import os
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.metrics.faithfulness import FaithfulnessEvaluator
from evalguard.metrics.relevance import RelevanceEvaluator
from evalguard.rag.pipeline import MockLLMClient, RAGPipeline
from evalguard.rag.vector_store import SimpleTFIDFVectorStore
from evalguard.runner import EvaluationRunner
from evalguard.storage.database import DatabaseManager


class FakeJudge:
    """Real-looking (non-mock) LLM judge."""
    is_mock = False

    def generate(self, prompt, system_prompt=None):
        return '{"score": 0.5, "reasoning": "ok"}'


def _run(rid, domain="hr", scorer="mock", ts="2026-01-01T00:00:00", simulated=False):
    return {"id": rid, "run_name": rid, "domain": domain, "timestamp": ts, "scorer": scorer,
            "is_simulated": simulated, "avg_faithfulness": 0.9}


class TestScorerTags(unittest.TestCase):
    def test_tags(self):
        a, c = "Students must attend 75% of classes.", ["Students must attend 75% of classes."]
        self.assertEqual(FaithfulnessEvaluator().evaluate(a, c)["scorer"], "heuristic")
        self.assertEqual(RelevanceEvaluator().evaluate("q", a)["scorer"], "heuristic")
        self.assertEqual(FaithfulnessEvaluator(MockLLMClient()).evaluate(a, c)["scorer"], "mock")
        self.assertEqual(RelevanceEvaluator(MockLLMClient()).evaluate("relevance q", a)["scorer"], "mock")
        self.assertEqual(FaithfulnessEvaluator(FakeJudge()).evaluate(a, c)["scorer"], "llm")
        self.assertEqual(RelevanceEvaluator(FakeJudge()).evaluate("q", a)["scorer"], "llm")


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = str(Path(self.tmp.name) / "t.db")
        self.db = DatabaseManager(db_path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_latest_run_skips_simulated_and_filters_scorer(self):
        self.db.save_run(_run("real_mock", scorer="mock", ts="2026-01-01T00:00:00"), [])
        self.db.save_run(_run("real_llm", scorer="llm", ts="2026-01-02T00:00:00"), [])
        self.db.save_run(_run("sim", scorer="mock", ts="2026-01-03T00:00:00", simulated=True), [])

        self.assertEqual(self.db.get_latest_run_for_domain("hr")["id"], "real_llm")  # sim skipped
        self.assertEqual(self.db.get_latest_run_for_domain("hr", scorer="mock")["id"], "real_mock")
        self.assertIsNone(self.db.get_latest_run_for_domain("hr", scorer="heuristic"))
        self.assertEqual(self.db.get_latest_run_for_domain("hr", exclude_id="real_llm")["id"], "real_mock")

    def test_domain_comparison_excludes_simulated(self):
        self.db.save_run(_run("real", ts="2026-01-01T00:00:00"), [])
        self.db.save_run(_run("sim", ts="2026-01-02T00:00:00", simulated=True), [])
        self.assertEqual([r["id"] for r in self.db.get_domain_comparison()], ["real"])

    def test_migration_of_legacy_db(self):
        legacy = str(Path(self.tmp.name) / "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.execute("""CREATE TABLE eval_runs (id TEXT PRIMARY KEY, run_name TEXT NOT NULL, domain TEXT NOT NULL,
            timestamp TEXT NOT NULL, model_name TEXT, embedding_model TEXT, total_questions INTEGER,
            avg_faithfulness REAL, avg_relevance REAL, avg_retrieval_hit_rate REAL, avg_mrr REAL,
            avg_latency_ms REAL, total_cost REAL, status TEXT)""")
        conn.execute("INSERT INTO eval_runs (id, run_name, domain, timestamp, model_name) VALUES "
                     "('old_real','r','hr','2026-01-01','gemini'),"
                     "('old_sim','s','hr','2026-01-02','simulated-degraded-model')")
        conn.commit()
        conn.close()

        db = DatabaseManager(db_path=legacy)
        DatabaseManager(db_path=legacy)  # idempotent second open
        self.assertEqual(db.get_run("old_real")["is_simulated"], 0)
        self.assertIsNone(db.get_run("old_real")["scorer"])
        self.assertEqual(db.get_run("old_sim")["is_simulated"], 1)


class TestVectorStoreClear(unittest.TestCase):
    def test_clear_keeps_cosine_space(self):
        try:
            import chromadb  # noqa: F401
        except ImportError:
            self.skipTest("chromadb not installed")
        from evalguard.rag.vector_store import ChromaVectorStore
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            store = ChromaVectorStore(persist_dir=d, collection_name="t_clear")
            self.assertEqual(store.collection.metadata.get("hnsw:space"), "cosine")
            store.clear()
            self.assertEqual(store.collection.metadata.get("hnsw:space"), "cosine")
            del store


class TestRunnerGating(unittest.TestCase):
    def _runner(self, db_path):
        r = EvaluationRunner(domain="hr", db_path=db_path)
        r.vector_store = SimpleTFIDFVectorStore()  # avoid embeddings / touching real chroma data
        r.rag_pipeline = RAGPipeline(vector_store=r.vector_store, llm_client=r.llm_client)
        return r

    def test_mock_warning_scorer_and_gating(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            dbp = str(Path(d) / "r.db")
            r1 = self._runner(dbp)
            self.assertTrue(r1.llm_client.is_mock, "test assumes no real API key is configured")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                out1 = r1.run_evaluation()
            self.assertTrue(any("MockLLMClient" in str(x.message) for x in w))
            self.assertEqual(out1["run"]["scorer"], "mock")
            self.assertIsNone(out1["drift_report"])  # no baseline yet

            # same scorer -> auto baseline works
            out2 = self._runner(dbp).run_evaluation()
            self.assertIsNotNone(out2["drift_report"])
            self.assertIsNone(out2["drift_skipped_reason"])

            # a baseline from a different scorer is refused
            db = DatabaseManager(db_path=dbp)
            db.save_run(_run("llm_base", scorer="llm", ts="2026-01-01T00:00:00"),
                        db.get_results_for_run(out1["run"]["id"]))
            out3 = self._runner(dbp).run_evaluation(baseline_run_id="llm_base")
            self.assertIsNone(out3["drift_report"])
            self.assertIn("differs", out3["drift_skipped_reason"])

            # simulated run is never auto-picked as baseline
            db.save_run(_run("sim", scorer="mock", ts="2999-01-01T00:00:00", simulated=True), [])
            out4 = self._runner(dbp).run_evaluation()
            self.assertNotEqual(db.get_latest_run_for_domain("hr", exclude_id=out4["run"]["id"],
                                                             scorer="mock")["id"], "sim")


if __name__ == "__main__":
    unittest.main()
