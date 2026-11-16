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


if __name__ == "__main__":
    unittest.main()
