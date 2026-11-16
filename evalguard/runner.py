import uuid
import warnings
from typing import Dict, Any, List, Optional

from evalguard.config import settings, utcnow_iso
from evalguard.dataset import SUITES, load_questions
from evalguard.ingestion.loader import DocumentLoader
from evalguard.ingestion.chunker import TextChunker
from evalguard.rag.vector_store import get_vector_store
from evalguard.rag.pipeline import QuotaExceeded, RAGPipeline, get_llm_client
from evalguard.metrics.faithfulness import FaithfulnessEvaluator
from evalguard.metrics.relevance import RelevanceEvaluator
from evalguard.metrics.retrieval import RetrievalEvaluator
from evalguard.metrics.safety import evaluate_safety
from evalguard.drift.detector import DriftDetector
from evalguard.storage.database import DatabaseManager
from evalguard.domains import get_domain_config
from evalguard.prompts import DEFAULT_PROMPT_NAME, DEFAULT_SYSTEM_PROMPT, prompt_hash

MAX_SKIPPED_FRACTION = 0.3  # a run where more than 30% of questions hit LLM errors is invalid, not "partial"


def _mean(values: List[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


class EvaluationRunner:
    """Orchestrates ingestion, RAG query execution, metric computation, drift checking, and storage."""

    def __init__(
        self,
        domain: str = "education",
        run_name: Optional[str] = None,
        db_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        prompt_name: Optional[str] = None,
        answer_model: Optional[str] = None,
        suite: str = "standard",
        question_limit: Optional[int] = None,
        experiment_id: Optional[str] = None,
        variant_label: Optional[str] = None,
    ):
        if suite not in SUITES:
            raise ValueError(f"suite must be one of {SUITES}")
        self.domain = domain.lower()
        self.domain_config = get_domain_config(self.domain)
        self.suite = suite
        self.question_limit = question_limit
        self.experiment_id = experiment_id
        self.variant_label = variant_label
        self.system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
        self.prompt_name = prompt_name or (DEFAULT_PROMPT_NAME if self.system_prompt == DEFAULT_SYSTEM_PROMPT else "Custom prompt")
        suffix = "" if suite == "standard" else f" [{suite}]"
        self.run_name = run_name or f"{self.domain_config.name} Benchmark{suffix} - {utcnow_iso()[:16].replace('T', ' ')}"
        self.db = DatabaseManager(db_path=db_path)
        self.vector_store = get_vector_store(collection_name=f"eval_{self.domain}")
        self.llm_client = get_llm_client("answer", model=answer_model)
        self.judge_client = get_llm_client("judge")
        self.rag_pipeline = RAGPipeline(vector_store=self.vector_store, llm_client=self.llm_client,
                                        system_prompt=self.system_prompt)

        # Domain-specific thresholds
        f_thresh = self.domain_config.faithfulness_threshold
        r_thresh = self.domain_config.relevance_threshold

        self.faithfulness_eval = FaithfulnessEvaluator(llm_client=self.judge_client, threshold=f_thresh)
        self.relevance_eval = RelevanceEvaluator(llm_client=self.judge_client, threshold=r_thresh)
        self.retrieval_eval = RetrievalEvaluator()
        self.drift_detector = DriftDetector(p_value_threshold=settings.DRIFT_P_VALUE_THRESHOLD)

    def ensure_indexed(self) -> int:
        """Index the domain only if its collection is empty. Returns number of stored chunks."""
        store = self.vector_store
        count = store.collection.count() if hasattr(store, "collection") else len(getattr(store, "documents", []))
        return count if count else self.ingest_domain_data()

    def ingest_domain_data(self) -> int:
        """Loads and chunks documents from data/{domain}/documents."""
        docs_dir = settings.DATA_DIR / self.domain / "documents"
        if not docs_dir.exists():
            raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

        loader = DocumentLoader(domain=self.domain)
        raw_docs = loader.load_directory(docs_dir)

        chunker = TextChunker(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
        chunks = chunker.chunk_documents(raw_docs)

        self.vector_store.clear()
        self.vector_store.add_documents(chunks)
        return len(chunks)

    def load_test_dataset(self) -> List[Dict[str, Any]]:
        return load_questions(self.domain, self.suite, db=self.db, limit=self.question_limit)

    def _same_basis(self, base_run: Dict[str, Any], run_data: Dict[str, Any]) -> Optional[str]:
        """None if a baseline is comparable with this run, else the reason it is not."""
        if base_run.get("scorer") != run_data["scorer"]:
            return f"Baseline scorer '{base_run.get('scorer')}' differs from current '{run_data['scorer']}'"
        if (base_run.get("suite") or "standard") != run_data["suite"]:
            return f"Baseline suite '{base_run.get('suite') or 'standard'}' differs from current '{run_data['suite']}'"
        return None

    def run_evaluation(
        self,
        baseline_run_id: Optional[str] = None,
        auto_compare_baseline: bool = True,
        progress=None
    ) -> Dict[str, Any]:
        """Executes the selected question suite and stores the run."""
        # 1. Ingest domain documents
        num_chunks = self.ingest_domain_data()

        # 2. Load questions
        test_data = self.load_test_dataset()
        if not test_data:
            raise ValueError(f"No questions found for domain '{self.domain}' in suite '{self.suite}'")

        if getattr(self.llm_client, "is_mock", False) or getattr(self.judge_client, "is_mock", False):
            warnings.warn(
                "MockLLMClient is active: judge scores are hard-coded constants, not real measurements. "
                "Set LLM_PROVIDER=openrouter and an API key, or use Ollama.",
                stacklevel=2
            )

        results: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        scorers = set()
        for i, item in enumerate(test_data):
            if progress:
                progress(i, len(test_data))
            question = item["question"]
            ground_truth = item["ground_truth"]

            try:
                rag_output = self.rag_pipeline.query(question=question)
                answer = rag_output["answer"]
                contexts = rag_output["contexts"]
                context_texts = [c["text"] for c in contexts]

                faith_res = self.faithfulness_eval.evaluate(answer=answer, contexts=context_texts)
                rel_res = self.relevance_eval.evaluate(question=question, answer=answer, ground_truth=ground_truth)
            except QuotaExceeded:
                raise  # a hard daily limit: every remaining question would fail the same way, so stop now
            except Exception as e:  # provider outage / rate limit after retries: skip the question, don't lose the run
                skipped.append({"question_id": str(item["id"]), "error": str(e)[:300]})
                continue

            scorers.update((faith_res["scorer"], rel_res["scorer"]))

            # retrieval only makes sense where a supporting passage should exist
            if item["answerable"] and item["expected_keywords"]:
                ret = self.retrieval_eval.evaluate_query(
                    retrieved_chunks=contexts, expected_keywords=item["expected_keywords"], ground_truth=ground_truth)
                hit, mrr = ret["hit_rate"], ret["mrr"]
            else:
                hit = mrr = None

            safety = evaluate_safety(item, answer, self.system_prompt)

            results.append({
                "question_id": str(item["id"]),
                "kind": item["kind"],
                "question": question,
                "ground_truth": ground_truth,
                "retrieved_contexts": contexts,
                "generated_answer": answer,
                "faithfulness_score": faith_res["score"],
                "faithfulness_reason": faith_res["reasoning"],
                "relevance_score": rel_res["score"],
                "relevance_reason": rel_res["reasoning"],
                "hit_rate": hit,
                "mrr": mrr,
                "safety_pass": None if safety is None else safety["pass"],
                "safety_reason": None if safety is None else safety["reason"],
                "latency_ms": rag_output["total_latency_ms"],
                "cost": rag_output["estimated_cost"],
            })

        if not results or len(skipped) / len(test_data) > MAX_SKIPPED_FRACTION:
            first = skipped[0]["error"] if skipped else "no results"
            raise RuntimeError(
                f"{len(skipped)} of {len(test_data)} questions failed with LLM errors (limit {int(MAX_SKIPPED_FRACTION * 100)}%). "
                f"First error: {first}"
            )

        # 3. Aggregate overall run metrics
        n = len(results)
        safety_vals = [None if r["safety_pass"] is None else float(r["safety_pass"]) for r in results]
        avg_hit, avg_mrr, avg_safety = _mean([r["hit_rate"] for r in results]), _mean([r["mrr"] for r in results]), _mean(safety_vals)

        run_id = str(uuid.uuid4())
        run_data = {
            "id": run_id,
            "run_name": self.run_name,
            "domain": self.domain,
            "timestamp": utcnow_iso(),
            "model_name": self.llm_client.model_name,
            "embedding_model": settings.EMBEDDING_MODEL,
            "total_questions": n,
            "avg_faithfulness": round(sum(r["faithfulness_score"] for r in results) / n, 4),
            "avg_relevance": round(sum(r["relevance_score"] for r in results) / n, 4),
            "avg_retrieval_hit_rate": None if avg_hit is None else round(avg_hit, 4),
            "avg_mrr": None if avg_mrr is None else round(avg_mrr, 4),
            "avg_safety": None if avg_safety is None else round(avg_safety, 4),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / n, 2),
            "total_cost": round(sum(r["cost"] for r in results), 6),
            "status": "PARTIAL" if skipped else "COMPLETED",
            "suite": self.suite,
            "prompt_name": self.prompt_name,
            "prompt_hash": prompt_hash(self.system_prompt),
            "experiment_id": self.experiment_id,
            "variant_label": self.variant_label,
            # judge model is part of the scorer identity: changing it makes runs non-comparable
            "scorer": "+".join(sorted(
                f"llm:{self.judge_client.model_name}" if s == "llm" else s for s in scorers
            )) or "none"
        }

        # 4. Save to Database
        self.db.save_run(run_data, results)

        # 5. Drift Detection vs Baseline. Only runs scored the same way on the same suite are comparable;
        # experiment variants are compared with each other, not against the live baseline.
        drift_report = None
        drift_skipped_reason = None
        target_baseline_id = baseline_run_id
        if not target_baseline_id and auto_compare_baseline and not self.experiment_id:
            latest_prev = self.db.get_latest_run_for_domain(
                domain=self.domain, exclude_id=run_id, scorer=run_data["scorer"], suite=self.suite
            )
            if latest_prev:
                target_baseline_id = latest_prev["id"]

        if target_baseline_id:
            base_run = self.db.get_run(target_baseline_id)
            baseline_results = []
            if base_run:
                reason = self._same_basis(base_run, run_data)
                if reason:
                    drift_skipped_reason = f"{reason}; drift comparison would be meaningless."
                else:
                    baseline_results = self.db.get_results_for_run(target_baseline_id)
            if baseline_results:
                drift_report = self.drift_detector.evaluate_run_drift(
                    baseline_results=baseline_results,
                    current_results=results
                )
                self.db.save_drift_records(target_baseline_id, run_id, drift_report)

        return {
            "run": run_data,
            "results": results,
            "indexed_chunks": num_chunks,
            "drift_report": drift_report,
            "drift_skipped_reason": drift_skipped_reason,
            "skipped": skipped,
        }
