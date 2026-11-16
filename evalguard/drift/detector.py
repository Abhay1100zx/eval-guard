import numpy as np
from scipy import stats
from typing import List, Dict, Any, Optional

class DriftDetector:
    """Detects statistical metric drift using Kolmogorov-Smirnov test and rolling statistics."""

    def __init__(self, p_value_threshold: float = 0.05, max_acceptable_drop: float = 0.10):
        self.p_value_threshold = p_value_threshold
        self.max_acceptable_drop = max_acceptable_drop

    def detect_ks_drift(self, baseline: List[float], current: List[float]) -> Dict[str, Any]:
        """Runs 2-sample Kolmogorov-Smirnov test between baseline and current distributions."""
        base_arr = np.array(baseline, dtype=float)
        curr_arr = np.array(current, dtype=float)

        if len(base_arr) == 0 or len(curr_arr) == 0:
            return {
                "ks_statistic": 0.0,
                "p_value": 1.0,
                "baseline_mean": 0.0,
                "current_mean": 0.0,
                "mean_delta": 0.0,
                "drop_percent": 0.0,
                "drift_detected": False,
                "reason": "Insufficient samples for KS test."
            }

        base_mean = float(np.mean(base_arr))
        curr_mean = float(np.mean(curr_arr))
        mean_delta = curr_mean - base_mean
        drop_ratio = (base_mean - curr_mean) / (abs(base_mean) + 1e-9)

        # If all values are identical in both
        if np.all(base_arr == base_arr[0]) and np.all(curr_arr == curr_arr[0]):
            identical = (base_arr[0] == curr_arr[0])
            is_drift = not identical and (drop_ratio > self.max_acceptable_drop)
            return {
                "ks_statistic": 0.0 if identical else 1.0,
                "p_value": 1.0 if identical else 0.0,
                "baseline_mean": round(base_mean, 4),
                "current_mean": round(curr_mean, 4),
                "mean_delta": round(mean_delta, 4),
                "drop_percent": round(drop_ratio * 100, 2),
                "drift_detected": bool(is_drift),
                "reason": "Constant distributions evaluated."
            }

        ks_res = stats.ks_2samp(base_arr, curr_arr)
        stat = float(ks_res.statistic)
        p_val = float(ks_res.pvalue)

        drift_detected = (p_val < self.p_value_threshold) and (drop_ratio > self.max_acceptable_drop)

        return {
            "ks_statistic": round(stat, 4),
            "p_value": round(p_val, 5),
            "baseline_mean": round(base_mean, 4),
            "current_mean": round(curr_mean, 4),
            "mean_delta": round(mean_delta, 4),
            "drop_percent": round(drop_ratio * 100, 2),
            "drift_detected": bool(drift_detected)
        }

    def compute_rolling_stats(self, values: List[float], window_size: int = 5) -> Dict[str, Any]:
        """Calculates rolling mean, standard deviation, and trend direction."""
        arr = np.array(values, dtype=float)
        if len(arr) == 0:
            return {"rolling_mean": [], "rolling_std": [], "trend": "stable"}

        win = min(window_size, len(arr))
        rolling_mean = []
        rolling_std = []

        for i in range(len(arr)):
            start_idx = max(0, i - win + 1)
            window_slice = arr[start_idx : i + 1]
            rolling_mean.append(round(float(np.mean(window_slice)), 4))
            rolling_std.append(round(float(np.std(window_slice)), 4))

        # Overall trend
        trend = "stable"
        if len(arr) >= 2:
            slope, _ = np.polyfit(np.arange(len(arr)), arr, 1)
            if slope < -0.02:
                trend = "degrading"
            elif slope > 0.02:
                trend = "improving"

        return {
            "rolling_mean": rolling_mean,
            "rolling_std": rolling_std,
            "trend": trend,
            "current_mean": round(float(np.mean(arr)), 4),
            "current_std": round(float(np.std(arr)), 4)
        }

    def evaluate_run_drift(
        self,
        baseline_results: List[Dict[str, Any]],
        current_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Comprehensive comparison across Faithfulness, Relevance, Hit Rate, and Latency."""
        metrics_to_check = ["faithfulness_score", "relevance_score", "hit_rate", "latency_ms"]
        drift_report = {}
        any_drift = False

        for metric in metrics_to_check:
            # None = not applicable (e.g. retrieval on unanswerable adversarial questions)
            base_vals = [r[metric] for r in baseline_results if r.get(metric) is not None]
            curr_vals = [r[metric] for r in current_results if r.get(metric) is not None]

            if not base_vals or not curr_vals:
                continue

            ks_analysis = self.detect_ks_drift(base_vals, curr_vals)
            rolling = self.compute_rolling_stats(curr_vals)

            # Latency is bad when it increases, others when they decrease
            if metric == "latency_ms":
                is_drift = (ks_analysis["p_value"] < self.p_value_threshold) and (ks_analysis["mean_delta"] > 500)
                severity = "CRITICAL_DRIFT" if is_drift else "NORMAL"
            else:
                is_drift = ks_analysis["drift_detected"]
                severity = "CRITICAL_DRIFT" if is_drift else ("WARNING" if ks_analysis["drop_percent"] > 5 else "NORMAL")

            if is_drift:
                any_drift = True

            drift_report[metric] = {
                "ks_statistic": ks_analysis["ks_statistic"],
                "p_value": ks_analysis["p_value"],
                "baseline_mean": ks_analysis["baseline_mean"],
                "current_mean": ks_analysis["current_mean"],
                "mean_delta": ks_analysis["mean_delta"],
                "severity": severity,
                "drift_detected": is_drift,
                "rolling_trend": rolling["trend"]
            }

        return {
            "overall_status": "DRIFT_DETECTED" if any_drift else "HEALTHY",
            "metrics": drift_report,
            "recommendation": (
                "Attention: Metric distribution shift detected. Review prompt modifications, chunking strategy, or LLM updates."
                if any_drift else "All evaluation metrics are stable and within acceptable bounds."
            )
        }
