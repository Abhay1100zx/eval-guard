import unittest
import sys
from pathlib import Path

# Ensure evalguard package is importable
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.drift.detector import DriftDetector

class TestDrift(unittest.TestCase):

    def test_ks_drift_identical(self):
        detector = DriftDetector(p_value_threshold=0.05)
        base = [0.85, 0.90, 0.88, 0.92, 0.89, 0.91]
        curr = [0.85, 0.90, 0.88, 0.92, 0.89, 0.91]
        res = detector.detect_ks_drift(base, curr)
        self.assertFalse(res["drift_detected"])
        self.assertGreater(res["p_value"], 0.05)

    def test_ks_drift_detected_on_degradation(self):
        detector = DriftDetector(p_value_threshold=0.05, max_acceptable_drop=0.10)
        # High baseline scores
        base = [0.95, 0.92, 0.94, 0.96, 0.91, 0.93, 0.95, 0.92, 0.97, 0.90]
        # Significantly degraded scores
        curr = [0.45, 0.40, 0.35, 0.42, 0.38, 0.48, 0.39, 0.41, 0.36, 0.44]

        res = detector.detect_ks_drift(base, curr)
        self.assertTrue(res["drift_detected"])
        self.assertLess(res["p_value"], 0.05)
        self.assertGreater(res["drop_percent"], 10.0)

    def test_rolling_statistics(self):
        detector = DriftDetector()
        scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
        rolling = detector.compute_rolling_stats(scores, window_size=3)
        self.assertEqual(len(rolling["rolling_mean"]), len(scores))
        self.assertEqual(rolling["trend"], "degrading")

    def test_full_run_drift_evaluation(self):
        detector = DriftDetector(p_value_threshold=0.05)
        baseline_results = [
            {"faithfulness_score": 0.92, "relevance_score": 0.90, "hit_rate": 1.0, "latency_ms": 120.0}
            for _ in range(10)
        ]
        # Degraded current results
        current_results = [
            {"faithfulness_score": 0.45, "relevance_score": 0.50, "hit_rate": 0.2, "latency_ms": 2500.0}
            for _ in range(10)
        ]

        report = detector.evaluate_run_drift(baseline_results, current_results)
        self.assertEqual(report["overall_status"], "DRIFT_DETECTED")
        self.assertIn("metrics", report)
        self.assertTrue(report["metrics"]["faithfulness_score"]["drift_detected"])

if __name__ == "__main__":
    unittest.main()
