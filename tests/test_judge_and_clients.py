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


class FakeStream:
    """What requests.post(..., stream=True) returns."""
    def __init__(self, lines=(), status=200, text=""):
        self.status_code, self._lines, self.text, self.closed, self.encoding = status, list(lines), text, False, None

    def iter_lines(self, decode_unicode=False):
        return iter(self._lines)

    def close(self):
        self.closed = True


def sse(*chunks):
    """Server-sent events the way OpenRouter/Gemini send them: keep-alive comments, blank separators, a [DONE] marker."""
    import json
    return [": keep-alive", *[x for c in chunks for x in (f"data: {json.dumps(c)}", "")], "data: [DONE]"]


class TestStreamingClients(unittest.TestCase):
    def openrouter(self):
        return OpenRouterLLMClient("k", "m:free")

    def test_openrouter_yields_pieces_as_they_arrive_and_closes_the_connection(self):
        res = FakeStream(sse({"choices": [{"delta": {"content": "18 "}}]}, {"choices": [{"delta": {}}]},
                             {"choices": [{"delta": {"content": "days"}}]}))
        with mock.patch("requests.post", return_value=res) as post:
            self.assertEqual(list(self.openrouter().stream_generate("p", "sys")), ["18 ", "days"])
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertEqual(post.call_args.kwargs["json"]["messages"][0], {"role": "system", "content": "sys"})
        self.assertTrue(res.closed)
        self.assertEqual(res.encoding, "utf-8")

    def test_openrouter_empty_stream_is_an_error(self):
        with mock.patch("requests.post", return_value=FakeStream(sse({"choices": [{"delta": {}}]}))):
            with self.assertRaises(RuntimeError):
                list(self.openrouter().stream_generate("p"))

    def test_openrouter_error_chunk_mid_stream_raises(self):
        res = FakeStream(sse({"choices": [{"delta": {"content": "a"}}]}, {"error": {"message": "boom"}}))
        with mock.patch("requests.post", return_value=res):
            gen = self.openrouter().stream_generate("p")
            self.assertEqual(next(gen), "a")
            with self.assertRaises(RuntimeError):
                next(gen)

    def test_stream_daily_limit_is_quota_exceeded_and_other_failures_are_plain_errors(self):
        with mock.patch("requests.post", return_value=FakeStream(status=429, text="Rate limit exceeded: free-models-per-day")) as post, \
                mock.patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(pipeline.QuotaExceeded):
                list(self.openrouter().stream_generate("p"))
        self.assertEqual(post.call_count, 1)  # no retries: the fallback chain moves on instead
        sleep.assert_not_called()
        with mock.patch("requests.post", return_value=FakeStream(status=503, text="busy")):
            with self.assertRaises(RuntimeError) as ctx:
                list(self.openrouter().stream_generate("p"))
        self.assertNotIsInstance(ctx.exception, pipeline.QuotaExceeded)
        import requests
        with mock.patch("requests.post", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(RuntimeError):
                list(self.openrouter().stream_generate("p"))

    def test_gemini_streams_from_the_sse_endpoint(self):
        res = FakeStream(sse({"candidates": [{"content": {"parts": [{"text": "18 "}]}}]},
                             {"candidates": [{"content": {"parts": [{"text": "days"}, {"text": "!"}]}}]}))
        with mock.patch("requests.post", return_value=res) as post:
            self.assertEqual(list(pipeline.GeminiLLMClient("k", "gemini-x").stream_generate("p", "sys")), ["18 ", "days!"])
        self.assertIn("gemini-x:streamGenerateContent?alt=sse", post.call_args.args[0])
        self.assertIn("sys", post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"])

    def test_ollama_streams_newline_delimited_json(self):
        import json
        lines = [json.dumps({"response": "18 ", "done": False}), "", json.dumps({"response": "days", "done": False}),
                 json.dumps({"response": "", "done": True}), json.dumps({"response": "ignored", "done": False})]
        with mock.patch("requests.post", return_value=FakeStream(lines)) as post:
            self.assertEqual(list(pipeline.OllamaLLMClient(model_name="phi3").stream_generate("p")), ["18 ", "days"])
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], "30s")
        with mock.patch("requests.post", return_value=FakeStream(['{"error": "out of memory"}'])):
            with self.assertRaises(RuntimeError):
                list(pipeline.OllamaLLMClient(model_name="phi3").stream_generate("p"))

    def test_mock_streams_word_by_word_and_a_plain_client_streams_in_one_piece(self):
        m = pipeline.MockLLMClient()
        prompt = "Context:\nEmployees receive 18 days of paid leave each year.\n\nQuestion: How many days?\n\nAnswer:"
        pieces = list(m.stream_generate(prompt))
        self.assertGreater(len(pieces), 3)
        self.assertEqual("".join(pieces).strip(), m.generate(prompt).strip())
        self.assertEqual(list(Fake("plain").stream_generate("p")), ["answer from plain"])


class StreamFake(Fake):
    """Streams `pieces`, raising `fail` after `fail_after` of them (immediately when 0)."""
    def __init__(self, name, pieces=("a ", "b"), fail=None, fail_after=0):
        super().__init__(name)
        self.pieces, self.stream_fail, self.fail_after = pieces, fail, fail_after

    def stream_generate(self, prompt, system_prompt=None):
        self.calls += 1
        for i, p in enumerate(self.pieces):
            if self.stream_fail and i >= self.fail_after:
                raise self.stream_fail
            yield p
        if self.stream_fail and self.fail_after >= len(self.pieces):
            raise self.stream_fail


class OtherStreamFake(StreamFake):
    pass


class TestFallbackStreaming(unittest.TestCase):
    def test_healthy_first_model_streams_and_nothing_is_skipped(self):
        a, b = StreamFake("a"), StreamFake("b")
        client = pipeline.FallbackLLMClient([a, b])
        self.assertEqual(list(client.stream_generate("p")), ["a ", "b"])
        self.assertEqual((client.model_name, client.skipped, b.calls), ("a", [], 0))

    def test_failure_before_the_first_piece_moves_to_the_next_model(self):
        a, g = StreamFake("or-1", fail=pipeline.QuotaExceeded("free-models-per-day")), OtherStreamFake("gemini", pieces=("hi",))
        client = pipeline.FallbackLLMClient([a, StreamFake("or-2"), g])
        self.assertEqual(list(client.stream_generate("p")), ["hi"])
        self.assertEqual((client.model_name, client.skipped), ("gemini", ["or-1: daily limit used up"]))

    def test_other_errors_try_the_next_model_even_from_the_same_provider(self):
        client = pipeline.FallbackLLMClient([StreamFake("or-1", fail=RuntimeError("HTTP 503")), StreamFake("or-2", pieces=("ok",))])
        self.assertEqual(list(client.stream_generate("p")), ["ok"])
        self.assertIn("or-1: HTTP 503", client.skipped[0])

    def test_failure_after_text_was_sent_is_raised_not_hidden_by_switching_models(self):
        a, b = StreamFake("a", fail=RuntimeError("dropped"), fail_after=1), StreamFake("b", pieces=("other",))
        client = pipeline.FallbackLLMClient([a, b])
        got = []
        with self.assertRaises(RuntimeError):
            for piece in client.stream_generate("p"):
                got.append(piece)
        self.assertEqual((got, b.calls, client.model_name), (["a "], 0, "a"))

    def test_quota_after_text_was_sent_is_raised_too(self):
        client = pipeline.FallbackLLMClient([StreamFake("a", fail=pipeline.QuotaExceeded("daily"), fail_after=1), OtherStreamFake("b")])
        with self.assertRaises(pipeline.QuotaExceeded):
            list(client.stream_generate("p"))

    def test_every_model_failing_reports_quota_when_a_limit_was_hit_and_remembers_it(self):
        a = StreamFake("or-1", fail=pipeline.QuotaExceeded("daily"))
        client = pipeline.FallbackLLMClient([a, OtherStreamFake("gemini", fail=RuntimeError("boom"))])
        with self.assertRaises(pipeline.QuotaExceeded) as ctx:
            list(client.stream_generate("p"))
        self.assertIn("or-1: daily limit used up", str(ctx.exception))
        self.assertIn("gemini: boom", str(ctx.exception))
        with self.assertRaises(pipeline.QuotaExceeded):
            list(client.stream_generate("p again"))
        self.assertEqual(a.calls, 1)  # not retried

    def test_non_streaming_clients_in_the_chain_still_work(self):
        client = pipeline.FallbackLLMClient([StreamFake("a", fail=RuntimeError("x")), Fake("plain")])
        self.assertEqual(list(client.stream_generate("p")), ["answer from plain"])


class TestSharedEmbedder(unittest.TestCase):
    def setUp(self):
        from evalguard.rag import vector_store
        self.vs = vector_store
        self.vs._EMBEDDERS.clear()
        self.addCleanup(self.vs._EMBEDDERS.clear)

    def test_the_model_is_loaded_once_per_process_not_once_per_vector_store(self):
        with mock.patch("chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction",
                        side_effect=lambda model_name: object()) as st:  # a fresh object per load
            a, b = self.vs.get_embedding_function("m"), self.vs.get_embedding_function("m")
            c = self.vs.get_embedding_function("other")
        self.assertIs(a, b)
        self.assertIsNot(a, c)
        self.assertEqual(st.call_count, 2)  # once for "m", once for "other"

    def test_falls_back_to_chromas_default_embedder_when_the_model_cannot_load(self):
        with mock.patch("chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction", side_effect=OSError("offline")), \
                mock.patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction") as default:
            self.assertIs(self.vs.get_embedding_function("m"), default.return_value)

    def test_warm_up_runs_the_model_once(self):
        with mock.patch("chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction") as st:
            self.vs.warm_up("m")
        st.return_value.assert_called_once_with(["warm up"])


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
