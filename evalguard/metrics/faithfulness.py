import re
import json
from typing import List, Dict, Any, Optional
from evalguard.metrics.judge import parse_judge_json

class FaithfulnessEvaluator:
    """Evaluates whether the generated answer is faithful to (grounded in) the retrieved context."""

    def __init__(self, llm_client=None, threshold: float = 0.70):
        self.llm_client = llm_client
        self.threshold = threshold

    def _heuristic_evaluate(self, answer: str, contexts: List[str]) -> Dict[str, Any]:
        if not answer.strip():
            return {"score": 0.0, "reasoning": "Answer is empty.", "is_faithful": False}
        if not contexts:
            return {"score": 0.0, "reasoning": "No contexts were provided to verify the answer.", "is_faithful": False}

        full_context = " ".join(contexts).lower()
        sentences = [s.strip() for s in re.split(r"[.!?]+", answer) if len(s.strip()) > 8]
        if not sentences:
            return {"score": 1.0, "reasoning": "Answer is very short and matches context.", "is_faithful": True}

        supported = 0
        unsupported_claims = []

        for s in sentences:
            tokens = [t for t in re.findall(r"\w+", s.lower()) if len(t) > 2]
            if not tokens:
                supported += 1
                continue
            matched = sum(1 for t in tokens if t in full_context)
            ratio = matched / len(tokens)
            if ratio >= 0.55:
                supported += 1
            else:
                unsupported_claims.append(s)

        score = round(supported / len(sentences), 4)
        is_faithful = score >= self.threshold
        reasoning = (
            f"All {len(sentences)} sentence claims are supported by context."
            if not unsupported_claims
            else f"{len(unsupported_claims)} claims may not be fully grounded in context: {'; '.join(unsupported_claims[:2])}"
        )

        return {
            "score": score,
            "reasoning": reasoning,
            "is_faithful": is_faithful
        }

    def evaluate(self, answer: str, contexts: List[str]) -> Dict[str, Any]:
        if self.llm_client and hasattr(self.llm_client, "generate"):
            try:
                context_str = "\n".join([f"- {c}" for c in contexts])
                prompt = (
                    "You are an expert AI evaluation judge assessing Faithfulness (Hallucination Detection).\n"
                    "Split the Candidate Answer into individual factual claims. A claim is supported only if the "
                    "Reference Context states it or directly implies it. Numbers, durations, amounts and conditions "
                    "must match exactly. Saying the context lacks the information is faithful.\n"
                    "Score = supported claims / total claims (1.0 = every claim supported, 0.0 = none).\n\n"
                    f"Reference Context:\n{context_str}\n\n"
                    f"Candidate Answer:\n{answer}\n\n"
                    "Return ONLY a valid JSON object in this exact schema with no extra markdown:\n"
                    "{\"score\": <float between 0.0 and 1.0>, \"reasoning\": \"<name any unsupported claim>\"}"
                )
                score, reasoning = parse_judge_json(self.llm_client.generate(prompt=prompt))
                return {
                    "score": round(max(0.0, min(1.0, score)), 4),
                    "reasoning": reasoning or "LLM-as-judge evaluation completed.",
                    "is_faithful": score >= self.threshold,
                    "scorer": "mock" if getattr(self.llm_client, "is_mock", False) else "llm"
                }
            except Exception:
                pass  # Fall back to heuristic evaluator

        res = self._heuristic_evaluate(answer, contexts)
        res["scorer"] = "heuristic"
        return res
