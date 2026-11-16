import re
import json
from typing import Dict, Any, Optional
from evalguard.metrics.judge import parse_judge_json

class RelevanceEvaluator:
    """Evaluates how relevant and directly responsive an answer is to a question and reference ground truth."""

    def __init__(self, llm_client=None, threshold: float = 0.70):
        self.llm_client = llm_client
        self.threshold = threshold

    def _token_overlap_score(self, text1: str, text2: str) -> float:
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "to", "in", "on", "of", "and", "or", "for", "with", "as", "by", "at", "that", "this"}
        tokens1 = [w for w in re.findall(r"\w+", text1.lower()) if w not in stopwords and len(w) >= 2]
        tokens2 = [w for w in re.findall(r"\w+", text2.lower()) if w not in stopwords and len(w) >= 2]

        if not tokens1 or not tokens2:
            return 0.5

        # Check exact and prefix (stem) matches
        matched = 0
        used_indices = set()
        for t1 in tokens1:
            for j, t2 in enumerate(tokens2):
                if j in used_indices:
                    continue
                # Exact match or prefix match for words > 4 chars (e.g. attend/attendance)
                if t1 == t2 or (len(t1) >= 4 and len(t2) >= 4 and (t1.startswith(t2[:4]) or t2.startswith(t1[:4]))):
                    matched += 1
                    used_indices.add(j)
                    break

        precision = matched / len(tokens1)
        recall = matched / len(tokens2)
        if precision + recall == 0:
            return 0.0
        f1 = 2 * (precision * recall) / (precision + recall)
        return round(f1, 4)

    def _heuristic_evaluate(self, question: str, answer: str, ground_truth: Optional[str] = None) -> Dict[str, Any]:
        if not answer.strip():
            return {"score": 0.0, "reasoning": "Answer is empty.", "is_relevant": False}

        q_overlap = self._token_overlap_score(answer, question)
        if ground_truth and ground_truth.strip():
            gt_overlap = self._token_overlap_score(answer, ground_truth)
            # Balanced synthesis of ground truth alignment and question intent
            combined = 0.5 * gt_overlap + 0.5 * q_overlap
            score = round(min(1.0, combined * 1.15), 4)
            reasoning = f"Answer achieves {score*100:.1f}% lexical/semantic alignment with ground truth and user query."
        else:
            score = round(min(1.0, q_overlap * 1.2), 4)
            reasoning = f"Answer addresses key question keywords with score {score*100:.1f}%."

        return {
            "score": max(0.0, min(1.0, score)),
            "reasoning": reasoning,
            "is_relevant": score >= self.threshold
        }

    def evaluate(self, question: str, answer: str, ground_truth: Optional[str] = None) -> Dict[str, Any]:
        if self.llm_client and hasattr(self.llm_client, "generate"):
            try:
                prompt = (
                    "You are an expert AI evaluation judge assessing Answer Relevance.\n"
                    "Determine whether the Candidate Answer directly and concisely addresses the Question"
                    " and, when a Ground Truth is given, conveys the same key facts (numbers, durations, conditions)."
                    " 1.0 = complete and correct, 0.5 = partially correct or missing a key fact, 0.0 = wrong or off-topic.\n\n"
                    f"Question: {question}\n\n"
                    f"Candidate Answer: {answer}\n\n"
                )
                if ground_truth:
                    prompt += f"Ground Truth Reference:\n{ground_truth}\n\n"

                prompt += (
                    "Return ONLY a valid JSON object in this exact schema with no extra markdown:\n"
                    "{\"score\": <float between 0.0 and 1.0>, \"reasoning\": \"<detailed explanation>\"}"
                )
                score, reasoning = parse_judge_json(self.llm_client.generate(prompt=prompt))
                return {
                    "score": round(max(0.0, min(1.0, score)), 4),
                    "reasoning": reasoning or "LLM-as-judge relevance evaluation completed.",
                    "is_relevant": score >= self.threshold,
                    "scorer": "mock" if getattr(self.llm_client, "is_mock", False) else "llm"
                }
            except Exception:
                pass

        res = self._heuristic_evaluate(question, answer, ground_truth)
        res["scorer"] = "heuristic"
        return res
