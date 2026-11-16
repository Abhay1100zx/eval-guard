import sqlite3
import json
from contextlib import contextmanager
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from evalguard.config import settings, utcnow_iso
from evalguard.prompts import DEFAULT_PROMPT_NAME, DEFAULT_SYSTEM_PROMPT

class DatabaseManager:
    """Manages SQLite storage for evaluation runs, per-question scores, and drift records."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        """Commit/rollback like sqlite3's own `with`, but also close (it leaks handles otherwise; locks the file on Windows)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Evaluation Runs Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model_name TEXT,
                embedding_model TEXT,
                total_questions INTEGER,
                avg_faithfulness REAL,
                avg_relevance REAL,
                avg_retrieval_hit_rate REAL,
                avg_mrr REAL,
                avg_latency_ms REAL,
                total_cost REAL,
                status TEXT
            );
            """)

            # Individual Question Results Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS eval_results (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                question_id TEXT,
                question TEXT,
                ground_truth TEXT,
                retrieved_contexts TEXT,
                generated_answer TEXT,
                faithfulness_score REAL,
                faithfulness_reason TEXT,
                relevance_score REAL,
                relevance_reason TEXT,
                hit_rate REAL,
                mrr REAL,
                latency_ms REAL,
                cost REAL,
                FOREIGN KEY (run_id) REFERENCES eval_runs (id) ON DELETE CASCADE
            );
            """)

            # Drift Records Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_records (
                id TEXT PRIMARY KEY,
                baseline_run_id TEXT,
                current_run_id TEXT,
                metric_name TEXT,
                ks_statistic REAL,
                p_value REAL,
                baseline_mean REAL,
                current_mean REAL,
                drift_detected INTEGER,
                timestamp TEXT
            );
            """)

            # Lightweight migration for DBs created before these columns existed
            cols = {r["name"] for r in cursor.execute("PRAGMA table_info(eval_runs)")}
            if "scorer" not in cols:
                cursor.execute("ALTER TABLE eval_runs ADD COLUMN scorer TEXT")
            if "is_simulated" not in cols:
                cursor.execute("ALTER TABLE eval_runs ADD COLUMN is_simulated INTEGER NOT NULL DEFAULT 0")
            cursor.execute("UPDATE eval_runs SET is_simulated = 1 WHERE model_name = 'simulated-degraded-model'")

            run_cols = {
                "prompt_name": "TEXT", "prompt_hash": "TEXT", "experiment_id": "TEXT",
                "suite": "TEXT", "avg_safety": "REAL", "variant_label": "TEXT",
            }
            for name, typ in run_cols.items():
                if name not in cols:
                    cursor.execute(f"ALTER TABLE eval_runs ADD COLUMN {name} {typ}")
            res_cols = {r["name"] for r in cursor.execute("PRAGMA table_info(eval_results)")}
            for name, typ in {"kind": "TEXT", "safety_pass": "INTEGER", "safety_reason": "TEXT"}.items():
                if name not in res_cols:
                    cursor.execute(f"ALTER TABLE eval_results ADD COLUMN {name} {typ}")

            cursor.execute("""CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, system_prompt TEXT NOT NULL,
                created_at TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS custom_questions (
                id TEXT PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL, question TEXT NOT NULL,
                ground_truth TEXT NOT NULL, expected_keywords TEXT NOT NULL DEFAULT '[]',
                must_not_contain TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, domain TEXT NOT NULL,
                suite TEXT NOT NULL, question_limit INTEGER, status TEXT NOT NULL,
                variants TEXT NOT NULL, created_at TEXT NOT NULL, error TEXT)""")
            if not cursor.execute("SELECT 1 FROM prompt_versions WHERE is_default = 1").fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO prompt_versions (id, name, system_prompt, created_at, is_default) VALUES (?, ?, ?, ?, 1)",
                    (str(uuid.uuid4()), DEFAULT_PROMPT_NAME, DEFAULT_SYSTEM_PROMPT, utcnow_iso()))

            conn.commit()

    def save_run(self, run_data: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
        run_id = run_data.get("id") or str(uuid.uuid4())
        timestamp = run_data.get("timestamp") or utcnow_iso()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            INSERT OR REPLACE INTO eval_runs (
                id, run_name, domain, timestamp, model_name, embedding_model,
                total_questions, avg_faithfulness, avg_relevance, avg_retrieval_hit_rate,
                avg_mrr, avg_latency_ms, total_cost, status, scorer, is_simulated,
                prompt_name, prompt_hash, experiment_id, suite, avg_safety, variant_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                run_data.get("run_name", f"Run-{timestamp[:10]}"),
                run_data.get("domain", "general"),
                timestamp,
                run_data.get("model_name", "unknown"),
                run_data.get("embedding_model", "all-MiniLM-L6-v2"),
                len(results),
                run_data.get("avg_faithfulness", 0.0),
                run_data.get("avg_relevance", 0.0),
                run_data.get("avg_retrieval_hit_rate"),
                run_data.get("avg_mrr"),
                run_data.get("avg_latency_ms", 0.0),
                run_data.get("total_cost", 0.0),
                run_data.get("status", "COMPLETED"),
                run_data.get("scorer"),
                1 if run_data.get("is_simulated") else 0,
                run_data.get("prompt_name"),
                run_data.get("prompt_hash"),
                run_data.get("experiment_id"),
                run_data.get("suite", "standard"),
                run_data.get("avg_safety"),
                run_data.get("variant_label"),
            ))

            for r in results:
                cursor.execute("""
                INSERT INTO eval_results (
                    id, run_id, question_id, question, ground_truth,
                    retrieved_contexts, generated_answer, faithfulness_score,
                    faithfulness_reason, relevance_score, relevance_reason,
                    hit_rate, mrr, latency_ms, cost, kind, safety_pass, safety_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    run_id,
                    r.get("question_id", ""),
                    r.get("question", ""),
                    r.get("ground_truth", ""),
                    json.dumps(r.get("retrieved_contexts", [])),
                    r.get("generated_answer", ""),
                    r.get("faithfulness_score", 0.0),
                    r.get("faithfulness_reason", ""),
                    r.get("relevance_score", 0.0),
                    r.get("relevance_reason", ""),
                    r.get("hit_rate"),
                    r.get("mrr"),
                    r.get("latency_ms", 0.0),
                    r.get("cost", 0.0),
                    r.get("kind", "standard"),
                    None if r.get("safety_pass") is None else (1 if r["safety_pass"] else 0),
                    r.get("safety_reason"),
                ))

        return run_id

    def get_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eval_runs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_results_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eval_results WHERE run_id = ?", (run_id,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["retrieved_contexts"] = json.loads(item["retrieved_contexts"])
                except Exception:
                    item["retrieved_contexts"] = []
                results.append(item)
            return results

    def save_drift_records(self, baseline_run_id: str, current_run_id: str, drift_data: Dict[str, Any]) -> None:
        metrics = drift_data.get("metrics", {})
        now = utcnow_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for metric_name, m_info in metrics.items():
                cursor.execute("""
                INSERT INTO drift_records (
                    id, baseline_run_id, current_run_id, metric_name,
                    ks_statistic, p_value, baseline_mean, current_mean,
                    drift_detected, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    baseline_run_id,
                    current_run_id,
                    metric_name,
                    m_info.get("ks_statistic", 0.0),
                    m_info.get("p_value", 1.0),
                    m_info.get("baseline_mean", 0.0),
                    m_info.get("current_mean", 0.0),
                    1 if m_info.get("drift_detected", False) else 0,
                    now
                ))
            conn.commit()

    def get_latest_run_for_domain(
        self, domain: str, exclude_id: Optional[str] = None, scorer: Optional[str] = None,
        suite: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Latest real run (not simulated, not part of an experiment); optional same-scorer / same-suite filter."""
        q = "SELECT * FROM eval_runs WHERE domain = ? AND is_simulated = 0 AND experiment_id IS NULL"
        args: list = [domain]
        if suite is not None:
            q += " AND COALESCE(suite, 'standard') = ?"
            args.append(suite)
        if exclude_id:
            q += " AND id != ?"
            args.append(exclude_id)
        if scorer is not None:
            q += " AND scorer = ?"
            args.append(scorer)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(q + " ORDER BY timestamp DESC LIMIT 1", args)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_runs_by_domain(self, domain: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM eval_runs WHERE domain = ? ORDER BY timestamp DESC LIMIT ?",
                (domain, limit)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_domain_comparison(self) -> List[Dict[str, Any]]:
        """Returns the most recent evaluation run metrics for each domain for comparative analysis."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT r.*
            FROM eval_runs r
            INNER JOIN (
                SELECT domain, MAX(timestamp) as max_time
                FROM eval_runs
                WHERE is_simulated = 0 AND experiment_id IS NULL AND COALESCE(suite, 'standard') = 'standard'
                GROUP BY domain
            ) latest ON r.domain = latest.domain AND r.timestamp = latest.max_time
            WHERE r.is_simulated = 0 AND r.experiment_id IS NULL AND COALESCE(r.suite, 'standard') = 'standard'
            ORDER BY r.avg_faithfulness DESC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_all_unique_domains(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT domain FROM eval_runs ORDER BY domain")
            return [row["domain"] for row in cursor.fetchall()]

    # ------------------------------------------------------------------ prompt library
    def list_prompts(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM prompt_versions ORDER BY is_default DESC, created_at").fetchall()
            return [dict(r) for r in rows]

    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM prompt_versions WHERE id = ?", (prompt_id,)).fetchone()
            return dict(row) if row else None

    def create_prompt(self, name: str, system_prompt: str) -> Dict[str, Any]:
        pid = str(uuid.uuid4())
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO prompt_versions (id, name, system_prompt, created_at, is_default) VALUES (?, ?, ?, ?, 0)",
                    (pid, name.strip(), system_prompt.strip(), utcnow_iso()))
        except sqlite3.IntegrityError:
            raise ValueError(f"A prompt named {name!r} already exists")
        return self.get_prompt(pid)

    def update_prompt(self, prompt_id: str, name: str, system_prompt: str) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cur = conn.execute("UPDATE prompt_versions SET name = ?, system_prompt = ? WHERE id = ?",
                                   (name.strip(), system_prompt.strip(), prompt_id))
                if cur.rowcount == 0:
                    return None
        except sqlite3.IntegrityError:
            raise ValueError(f"A prompt named {name!r} already exists")
        return self.get_prompt(prompt_id)

    def delete_prompt(self, prompt_id: str) -> bool:
        """The default prompt can't be deleted."""
        with self._get_connection() as conn:
            return conn.execute("DELETE FROM prompt_versions WHERE id = ? AND is_default = 0", (prompt_id,)).rowcount > 0

    # ------------------------------------------------------------------ custom questions
    @staticmethod
    def _question_row(row) -> Dict[str, Any]:
        d = dict(row)
        d["expected_keywords"] = json.loads(d.get("expected_keywords") or "[]")
        d["must_not_contain"] = json.loads(d.get("must_not_contain") or "[]")
        return d

    def list_custom_questions(self, domain: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        q, args = "SELECT * FROM custom_questions WHERE 1=1", []
        if domain:
            q += " AND domain = ?"
            args.append(domain)
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        with self._get_connection() as conn:
            return [self._question_row(r) for r in conn.execute(q + " ORDER BY created_at", args).fetchall()]

    def get_custom_question(self, qid: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM custom_questions WHERE id = ?", (qid,)).fetchone()
            return self._question_row(row) if row else None

    def create_custom_question(self, data: Dict[str, Any]) -> Dict[str, Any]:
        qid = "custom_" + uuid.uuid4().hex[:10]
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO custom_questions (id, domain, kind, question, ground_truth, expected_keywords, must_not_contain, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (qid, data["domain"], data["kind"], data["question"].strip(), data["ground_truth"].strip(),
                 json.dumps(data.get("expected_keywords", [])), json.dumps(data.get("must_not_contain", [])), utcnow_iso()))
        return self.get_custom_question(qid)

    def update_custom_question(self, qid: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE custom_questions SET domain = ?, kind = ?, question = ?, ground_truth = ?,"
                " expected_keywords = ?, must_not_contain = ? WHERE id = ?",
                (data["domain"], data["kind"], data["question"].strip(), data["ground_truth"].strip(),
                 json.dumps(data.get("expected_keywords", [])), json.dumps(data.get("must_not_contain", [])), qid))
            if cur.rowcount == 0:
                return None
        return self.get_custom_question(qid)

    def delete_custom_question(self, qid: str) -> bool:
        with self._get_connection() as conn:
            return conn.execute("DELETE FROM custom_questions WHERE id = ?", (qid,)).rowcount > 0

    # ------------------------------------------------------------------ experiments
    @staticmethod
    def _experiment_row(row) -> Dict[str, Any]:
        d = dict(row)
        d["variants"] = json.loads(d["variants"])
        return d

    def create_experiment(self, exp: Dict[str, Any]) -> str:
        exp_id = exp.get("id") or str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO experiments (id, name, kind, domain, suite, question_limit, status, variants, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (exp_id, exp["name"], exp["kind"], exp["domain"], exp["suite"], exp.get("question_limit"),
                 exp.get("status", "queued"), json.dumps(exp["variants"]), utcnow_iso()))
        return exp_id

    def update_experiment_status(self, exp_id: str, status: str, error: Optional[str] = None) -> None:
        with self._get_connection() as conn:
            conn.execute("UPDATE experiments SET status = ?, error = ? WHERE id = ?", (status, error, exp_id))

    def get_experiment(self, exp_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
            return self._experiment_row(row) if row else None

    def list_experiments(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._experiment_row(r) for r in rows]

    def get_runs_for_experiment(self, exp_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM eval_runs WHERE experiment_id = ? ORDER BY timestamp", (exp_id,)).fetchall()
            return [dict(r) for r in rows]
