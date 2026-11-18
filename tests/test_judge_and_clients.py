import sys
import unittest
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.ingestion.chunker import TextChunker
from evalguard.metrics.judge import parse_judge_json
from evalguard.metrics.retrieval import RetrievalEvaluator
from evalguard.rag import pipeline
from evalguard.rag.pipeline import OpenRouterLLMClient


class TestJudgeParsing(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(parse_judge_json('{"score": 0.8, "reasoning": "ok"}'), (0.8, "ok"))
        self.assertEqual(parse_judge_json('```json\n{"score": 1, "reasoning": "x"}\n```')[0], 1.0)
        self.assertEqual(parse_judge_json('<think>hmm {"a":1}</think>\nVerdict: {"score": 0.4, "reasoning": "r"}')[0], 0.4)
        # nested braces inside reasoning broke the old non-greedy regex
        self.assertEqual(parse_judge_json('{"score": 0.6, "reasoning": "claim {x} unsupported"}')[0], 0.6)
        self.assertEqual(parse_judge_json("The score: 0.7 overall")[0], 0.7)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_judge_json("I cannot evaluate this.")


class TestRetrievalStrictness(unittest.TestCase):
    def test_needs_majority_of_keywords(self):
        chunk = "Employees receive 18 days of PTO each year."
        # 1 of 3 keywords used to count as a hit; now 60% required
        self.assertFalse(RetrievalEvaluator.is_chunk_relevant(chunk, ["18 days", "1.5 days", "March 31"]))
        self.assertTrue(RetrievalEvaluator.is_chunk_relevant(chunk, ["18 days", "PTO"]))
        self.assertTrue(RetrievalEvaluator.is_chunk_relevant("Stipend is $500\nwithin 90  days", ["$500", "90 days"]))

    def test_empty_labels_not_relevant(self):
        self.assertFalse(RetrievalEvaluator.is_chunk_relevant("anything", [], None))


class TestChunker(unittest.TestCase):
    def test_overlap_preserved_when_snapping(self):
        text = " ".join(f"Sentence number {i} ends here." for i in range(60))
        chunks = TextChunker(chunk_size=200, chunk_overlap=40).split_text(text)
        self.assertGreater(len(chunks), 3)
        for a, b in zip(chunks, chunks[1:]):
            self.assertTrue(set(a.split()[-4:]) & set(b.split()[:8]), "adjacent chunks share overlapping text")


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._b, self.text = status, body, str(body)

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestOpenRouterClient(unittest.TestCase):
    def _client(self):
        return OpenRouterLLMClient("k", "vendor/model:free")

    def test_success_and_free_flag(self):
        ok = FakeResp(200, {"choices": [{"message": {"content": " hi "}}]})
        with mock.patch("requests.post", return_value=ok) as post:
            c = self._client()
            self.assertEqual(c.generate("p", "sys"), "hi")
            self.assertTrue(c.is_free)
            sent = post.call_args.kwargs["json"]
            self.assertEqual(sent["messages"][0], {"role": "system", "content": "sys"})
            self.assertEqual(sent["temperature"], 0)
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer k")

    def test_retries_on_429_then_succeeds(self):
        seq = [FakeResp(429, {}), FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})]
        with mock.patch("requests.post", side_effect=seq), mock.patch.object(pipeline.time, "sleep"):
            self.assertEqual(self._client().generate("p"), "ok")

    def test_gives_up_after_retries(self):
        with mock.patch("requests.post", return_value=FakeResp(429, {})), mock.patch.object(pipeline.time, "sleep"):
            with self.assertRaises(RuntimeError):
                self._client().generate("p")

    def test_daily_quota_fails_fast_without_retrying(self):
        body = {"error": {"message": "Rate limit exceeded: free-models-per-day."}}
        with mock.patch("requests.post", return_value=FakeResp(429, body)) as post, mock.patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(pipeline.QuotaExceeded) as ctx:
                self._client().generate("p")
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("daily", str(ctx.exception))

    def test_embedded_error_body_raises(self):
        with mock.patch("requests.post", return_value=FakeResp(200, {"error": {"message": "bad"}})):
            with self.assertRaises(RuntimeError):
                self._client().generate("p")


class Fake(pipeline.BaseLLMClient):
    """A client that answers or raises on demand."""
    def __init__(self, name, fail=None):
        self.model_name, self.fail, self.calls = name, fail, 0

    def generate(self, prompt, system_prompt=None):
        self.calls += 1
        if self.fail:
            raise self.fail
        return f"answer from {self.model_name}"


class OtherProvider(Fake):
    pass


Quota = pipeline.QuotaExceeded("free-models-per-day")


class TestFallback(unittest.TestCase):
    def test_first_model_answers_when_healthy(self):
        a, b = Fake("a"), Fake("b")
        client = pipeline.FallbackLLMClient([a, b])
        self.assertEqual(client.generate("p"), "answer from a")
        self.assertEqual((client.model_name, client.skipped, b.calls), ("a", [], 0))

    def test_quota_moves_to_another_provider_and_skips_same_provider_siblings(self):
        a1, a2, g = Fake("or-1", Quota), Fake("or-2"), OtherProvider("gemini")
        client = pipeline.FallbackLLMClient([a1, a2, g])
        self.assertEqual(client.generate("p"), "answer from gemini")
        self.assertEqual(client.model_name, "gemini")
        self.assertEqual(client.skipped, ["or-1: daily limit used up"])
        self.assertEqual(a2.calls, 0)  # same provider, same account-wide limit

    def test_other_errors_try_the_next_model_even_from_the_same_provider(self):
        a1, a2 = Fake("or-1", RuntimeError("HTTP 502")), Fake("or-2")
        client = pipeline.FallbackLLMClient([a1, a2])
        self.assertEqual(client.generate("p"), "answer from or-2")
        self.assertIn("or-1: HTTP 502", client.skipped[0])

    def test_exhausted_provider_is_not_retried_on_the_second_call(self):
        a, g = Fake("or-1", Quota), OtherProvider("gemini")
        client = pipeline.FallbackLLMClient([a, g])
        client.generate("one")
        client.generate("two")
        self.assertEqual((a.calls, g.calls), (1, 2))
        self.assertEqual(client.skipped, ["or-1: daily limit used up"])

    def test_everything_failing_reports_quota_when_a_limit_was_hit(self):
        client = pipeline.FallbackLLMClient([Fake("or-1", Quota), OtherProvider("gemini", RuntimeError("boom"))])
        with self.assertRaises(pipeline.QuotaExceeded) as ctx:
            client.generate("p")
        self.assertIn("or-1: daily limit used up", str(ctx.exception))
        self.assertIn("gemini: boom", str(ctx.exception))

    def test_everything_failing_without_a_limit_is_a_plain_error(self):
        client = pipeline.FallbackLLMClient([Fake("a", RuntimeError("x")), OtherProvider("b", RuntimeError("y"))])
        with self.assertRaises(RuntimeError) as ctx:
            client.generate("p")
        self.assertNotIsInstance(ctx.exception, pipeline.QuotaExceeded)

    def test_gemini_per_day_wording_is_recognised_as_a_daily_limit(self):
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded ... GenerateRequestsPerDayPerProjectPerModel-FreeTier"}}
        with mock.patch("requests.post", return_value=FakeResp(429, body)), mock.patch.object(pipeline.time, "sleep"):
            with self.assertRaises(pipeline.QuotaExceeded):
                pipeline.GeminiLLMClient("key").generate("p")


class TestOllama(unittest.TestCase):
    def test_context_window_is_capped_so_small_machines_can_load_the_model(self):
        with mock.patch("requests.post", return_value=FakeResp(200, {"response": " hi "})) as post, \
                mock.patch.object(pipeline.settings, "OLLAMA_NUM_CTX", 2048):
            self.assertEqual(pipeline.OllamaLLMClient(model_name="phi3").generate("p"), "hi")
        self.assertEqual(post.call_args.kwargs["json"]["options"], {"num_ctx": 2048})
        self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], "30s")  # frees ~3 GB soon after use

    def test_available_needs_the_server_up_and_the_model_pulled(self):
        tags = {"models": [{"name": "phi3:latest"}, {"name": "mistral:latest"}]}
        with mock.patch("requests.get", return_value=FakeResp(200, tags)):
            self.assertTrue(pipeline.OllamaLLMClient(model_name="phi3").available())
            self.assertFalse(pipeline.OllamaLLMClient(model_name="llama3").available())
        with mock.patch("requests.get", side_effect=ConnectionError("refused")):
            self.assertFalse(pipeline.OllamaLLMClient(model_name="phi3").available())


class TestChatClientChain(unittest.TestCase):
    def chain(self, ollama=False, **env):
        base = dict(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="k", OPENROUTER_MODEL="m-answer:free",
                    OPENROUTER_JUDGE_MODEL="m-judge:free", GEMINI_API_KEY="", GEMINI_MODEL="gemini-2.5-flash", OLLAMA_MODEL="llama3")
        with mock.patch.multiple(pipeline.settings, **{**base, **env}), \
                mock.patch.object(pipeline.OllamaLLMClient, "available", return_value=ollama):
            return pipeline.get_chat_client("answer")

    def names(self, client):
        return [c.model_name for c in getattr(client, "clients", [client])]

    def test_openrouter_primary_then_other_free_models_gemini_and_ollama(self):
        client = self.chain(ollama=True, GEMINI_API_KEY="real-key")
        self.assertEqual(self.names(client), ["m-answer:free", "m-judge:free", "openrouter/free", "gemini-2.5-flash", "llama3"])

    def test_gemini_and_ollama_are_left_out_when_not_set_up(self):
        self.assertEqual(self.names(self.chain()), ["m-answer:free", "m-judge:free", "openrouter/free"])

    def test_mock_provider_gets_no_fallbacks(self):
        client = self.chain(ollama=True, LLM_PROVIDER="mock")
        self.assertTrue(client.is_mock)
        self.assertEqual(self.names(client), ["mock-eval-llm"])


if __name__ == "__main__":
    unittest.main()
