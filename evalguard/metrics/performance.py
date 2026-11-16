from typing import Dict, Any, List

class PerformanceTracker:
    """Tracks latency (retrieval, generation, end-to-end) and estimated token costs."""

    # Approximate pricing per 1K tokens ($)
    GEMINI_15_FLASH_INPUT_PRICE_PER_1K = 0.000075
    GEMINI_15_FLASH_OUTPUT_PRICE_PER_1K = 0.000300
    OLLAMA_PRICE = 0.0

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def calculate_cost(
        cls,
        prompt_text: str,
        response_text: str,
        provider: str = "gemini",
        free: bool = False
    ) -> float:
        """`free` covers mock, local Ollama and OpenRouter ':free' models. Judge calls are not costed."""
        if free or provider == "ollama":
            return 0.0

        in_tokens = cls.estimate_tokens(prompt_text)
        out_tokens = cls.estimate_tokens(response_text)

        cost = (
            (in_tokens / 1000.0) * cls.GEMINI_15_FLASH_INPUT_PRICE_PER_1K +
            (out_tokens / 1000.0) * cls.GEMINI_15_FLASH_OUTPUT_PRICE_PER_1K
        )
        return round(cost, 7)

    @classmethod
    def summarize_performance(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {
                "avg_retrieval_latency_ms": 0.0,
                "avg_generation_latency_ms": 0.0,
                "avg_total_latency_ms": 0.0,
                "p95_total_latency_ms": 0.0,
                "total_estimated_cost": 0.0
            }

        retrievals = [r.get("retrieval_latency_ms", 0.0) for r in records]
        generations = [r.get("generation_latency_ms", 0.0) for r in records]
        totals = sorted([r.get("total_latency_ms", 0.0) for r in records])
        costs = [r.get("cost", 0.0) for r in records]

        p95_idx = int(len(totals) * 0.95)
        p95_val = totals[min(p95_idx, len(totals) - 1)]

        return {
            "avg_retrieval_latency_ms": round(sum(retrievals) / len(retrievals), 2),
            "avg_generation_latency_ms": round(sum(generations) / len(generations), 2),
            "avg_total_latency_ms": round(sum(totals) / len(totals), 2),
            "p95_total_latency_ms": round(p95_val, 2),
            "total_estimated_cost": round(sum(costs), 6)
        }
