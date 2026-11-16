import math
import re
from typing import List, Dict, Any, Optional

class RetrievalEvaluator:
    """Evaluates retrieval quality including Hit Rate, MRR, and Precision@k."""

    @staticmethod
    def is_chunk_relevant(chunk_text: str, expected_keywords: List[str], ground_truth: Optional[str] = None) -> bool:
        norm = RetrievalEvaluator._norm
        chunk_n = norm(chunk_text)
        if expected_keywords:
            # Relevant only if at least 60% of the expected keywords appear (was: any 1 of 3)
            matches = sum(1 for kw in expected_keywords if norm(kw) in chunk_n)
            return matches >= math.ceil(0.6 * len(expected_keywords))

        # No keywords labelled: fall back to strong ground-truth word overlap
        if ground_truth:
            gt_words = [w for w in norm(ground_truth).split() if len(w) > 3]
            if gt_words:
                chunk_words = set(chunk_n.split())
                return sum(1 for w in gt_words if w in chunk_words) / len(gt_words) >= 0.6

        return False

    @staticmethod
    def _norm(text: str) -> str:
        """Lowercase and collapse punctuation/whitespace so '$500' vs '$ 500' or line breaks don't matter."""
        return re.sub(r"[^\w$%.]+", " ", text.lower()).strip()

    def evaluate_query(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        expected_keywords: Optional[List[str]] = None,
        ground_truth: Optional[str] = None
    ) -> Dict[str, Any]:
        keywords = expected_keywords or []
        k = len(retrieved_chunks)
        if k == 0:
            return {
                "hit_rate": 0.0,
                "mrr": 0.0,
                "precision_at_k": 0.0,
                "relevant_chunks_count": 0,
                "k": 0
            }

        first_relevant_rank = None
        relevant_count = 0

        for rank, chunk in enumerate(retrieved_chunks, start=1):
            text = chunk.get("text", "")
            if self.is_chunk_relevant(text, keywords, ground_truth):
                relevant_count += 1
                if first_relevant_rank is None:
                    first_relevant_rank = rank

        hit_rate = 1.0 if relevant_count > 0 else 0.0
        mrr = (1.0 / first_relevant_rank) if first_relevant_rank is not None else 0.0
        precision_at_k = relevant_count / k if k > 0 else 0.0

        return {
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            "precision_at_k": round(precision_at_k, 4),
            "relevant_chunks_count": relevant_count,
            "k": k
        }
