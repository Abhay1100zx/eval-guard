import unittest
import sys
from pathlib import Path

# Ensure evalguard package is importable
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.metrics.faithfulness import FaithfulnessEvaluator
from evalguard.metrics.relevance import RelevanceEvaluator
from evalguard.metrics.retrieval import RetrievalEvaluator
from evalguard.metrics.performance import PerformanceTracker

class TestMetrics(unittest.TestCase):

    def test_faithfulness_grounded(self):
        evaluator = FaithfulnessEvaluator(threshold=0.70)
        contexts = [
            "Apex University requires students to attend at least 75% of classes to avoid an attendance warning."
        ]
        answer = "Students at Apex University must attend 75% of their classes to avoid receiving an attendance warning."
        result = evaluator.evaluate(answer=answer, contexts=contexts)
        self.assertGreaterEqual(result["score"], 0.70)
        self.assertTrue(result["is_faithful"])

    def test_faithfulness_hallucination(self):
        evaluator = FaithfulnessEvaluator(threshold=0.70)
        contexts = [
            "Apex University requires students to attend at least 75% of classes to avoid an attendance warning."
        ]
        answer = "Students must pay an additional 5000 dollars penalty fee and their passport will be revoked immediately."
        result = evaluator.evaluate(answer=answer, contexts=contexts)
        self.assertLess(result["score"], 0.70)
        self.assertFalse(result["is_faithful"])

    def test_relevance_good_answer(self):
        evaluator = RelevanceEvaluator(threshold=0.70)
        question = "What is the minimum attendance required at the college?"
        ground_truth = "Students must attend at least 75% of classes."
        answer = "The minimum attendance percentage required is 75% of scheduled classes."

        result = evaluator.evaluate(question=question, answer=answer, ground_truth=ground_truth)
        self.assertGreaterEqual(result["score"], 0.50)
        self.assertIn("75%", answer)

    def test_retrieval_hit_rate_and_mrr(self):
        evaluator = RetrievalEvaluator()
        retrieved = [
            {"text": "Dorm quiet hours start at 10 PM on weekdays."},
            {"text": "Undergraduates must enroll in 12 credit hours per semester to be full-time."},
            {"text": "Dining plans are mandatory for freshmen."}
        ]
        expected_keywords = ["12 credit hours", "full-time"]

        res = evaluator.evaluate_query(retrieved_chunks=retrieved, expected_keywords=expected_keywords)
        self.assertEqual(res["hit_rate"], 1.0)
        # Relevant chunk was at rank 2 -> MRR = 1/2 = 0.5
        self.assertEqual(res["mrr"], 0.5)
        self.assertEqual(res["relevant_chunks_count"], 1)

    def test_performance_cost_and_latency(self):
        cost = PerformanceTracker.calculate_cost("Short prompt", "Short response", provider="gemini")
        self.assertGreaterEqual(cost, 0.0)

        summary = PerformanceTracker.summarize_performance([
            {"retrieval_latency_ms": 20.0, "generation_latency_ms": 100.0, "total_latency_ms": 120.0, "cost": 0.0001},
            {"retrieval_latency_ms": 30.0, "generation_latency_ms": 110.0, "total_latency_ms": 140.0, "cost": 0.0001}
        ])
        self.assertEqual(summary["avg_total_latency_ms"], 130.0)
        self.assertEqual(summary["avg_retrieval_latency_ms"], 25.0)

if __name__ == "__main__":
    unittest.main()
