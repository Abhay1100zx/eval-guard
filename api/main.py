import sys
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Ensure evalguard package is in Python search path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from typing import Optional, List, Literal
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from evalguard.config import settings, utcnow_iso
from evalguard.auth import require_user, auth_disabled
from evalguard.runner import EvaluationRunner
from evalguard.storage.database import DatabaseManager
from evalguard.rag.pipeline import RAGPipeline, get_llm_client
from evalguard.rag.vector_store import get_vector_store
from evalguard.metrics.faithfulness import FaithfulnessEvaluator
from evalguard.metrics.relevance import RelevanceEvaluator
from evalguard.drift.detector import DriftDetector
from evalguard.domains import DOMAINS_REGISTRY, DOMAIN_DISPLAY_NAMES
from evalguard.dataset import keywords_missing, load_builtin, normalize_item

app = FastAPI(
    title="EvalGuard AI API",
    description="Multi-domain RAG evaluation, benchmarking and drift detection. All routes except /health require a Clerk session token.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,  # Bearer tokens, no cookies
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

db = DatabaseManager()
protected = [Depends(require_user)]

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXT = {".txt", ".md", ".pdf"}

# ---------------------------------------------------------------- background jobs
# One worker: evaluations clear/reindex per-domain Chroma collections and hit rate-limited free LLMs,
# so running them serially is both safer and simpler.
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: "OrderedDict[str, dict]" = OrderedDict()
MAX_JOBS = 100


def _new_job(kind: str, domains: List[str]) -> dict:
    job = {"id": str(uuid.uuid4()), "kind": kind, "domains": domains, "status": "queued",
           "progress": {"domain": None, "current": 0, "total": 0, "domains_done": 0, "domains_total": len(domains)},
           "results": [], "error": None, "created_at": utcnow_iso(), "finished_at": None}
    _jobs[job["id"]] = job
    while len(_jobs) > MAX_JOBS:
        _jobs.popitem(last=False)
    return job


def _run_job(job: dict, run_name: Optional[str], baseline_run_id: Optional[str], runner_kwargs: Optional[dict] = None):
    job["status"] = "running"
    try:
        for dom in job["domains"]:
            job["progress"].update(domain=dom, current=0, total=0)
            try:
                runner = EvaluationRunner(domain=dom, run_name=run_name, **(runner_kwargs or {}))
                out = runner.run_evaluation(
                    baseline_run_id=baseline_run_id,
                    progress=lambda i, n: job["progress"].update(current=i, total=n),
                )
                job["results"].append({"domain": dom, "status": "SUCCESS", "run": out["run"],
                                       "indexed_chunks": out["indexed_chunks"],
                                       "drift_report": out["drift_report"],
                                       "drift_skipped_reason": out["drift_skipped_reason"],
                                       "skipped": out["skipped"]})
            except Exception as e:  # one failing domain must not abort a batch
                job["results"].append({"domain": dom, "status": "FAILED", "error": str(e)})
            job["progress"]["domains_done"] += 1
        failed = [r for r in job["results"] if r["status"] == "FAILED"]
        job["status"] = "failed" if len(failed) == len(job["results"]) else "done"
        if job["status"] == "failed":
            job["error"] = failed[0]["error"] if failed else "unknown"
    except Exception as e:
        job["status"], job["error"] = "failed", str(e)
    finally:
        job["finished_at"] = utcnow_iso()


def _validate_domain(domain: str) -> str:
    key = domain.lower().strip()
    if key not in DOMAINS_REGISTRY:
        raise HTTPException(400, f"Invalid domain '{domain}'. Must be one of: {list(DOMAINS_REGISTRY.keys())}")
    return key


# ---------------------------------------------------------------- models
class EvalRunRequest(BaseModel):
    domain: str = Field(default="education", description="Domain identifier")
    run_name: Optional[str] = Field(default=None, max_length=200)
    baseline_run_id: Optional[str] = Field(default=None, description="Optional baseline run id for drift comparison")
    suite: Literal["standard", "adversarial", "all"] = "standard"
    prompt_id: Optional[str] = Field(default=None, description="Prompt-library entry to use instead of the default")
    model: Optional[str] = Field(default=None, max_length=120, description="Override the answering model (OpenRouter)")
    question_limit: Optional[int] = Field(default=None, ge=1, le=100)


class LiveQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    domain: str = Field(default="education")
    top_k: int = Field(default=3, ge=1, le=20)


# ---------------------------------------------------------------- public
@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------- protected
@app.get("/me", dependencies=protected)
def me(user: dict = Depends(require_user)):
    return {"user_id": user.get("sub"), "dev_mode": bool(user.get("dev"))}


@app.get("/status", dependencies=protected)
def system_status():
    answer, judge = get_llm_client("answer"), get_llm_client("judge")
    return {
        "version": app.version,
        "llm_provider": settings.LLM_PROVIDER,
        "answer_model": answer.model_name,
        "judge_model": judge.model_name,
        "is_mock": bool(answer.is_mock or judge.is_mock),
        "embedding_model": settings.EMBEDDING_MODEL,
        "total_domains": len(DOMAINS_REGISTRY),
        "auth_disabled": auth_disabled(),
    }


@app.get("/domains", dependencies=protected)
def get_supported_domains():
    output = [{
        "key": c.key, "name": c.name, "icon": c.icon, "description": c.description,
        "faithfulness_threshold": c.faithfulness_threshold, "relevance_threshold": c.relevance_threshold,
        "safeguard_notice": c.safeguard_notice, "sample_question": c.sample_question,
    } for c in DOMAINS_REGISTRY.values()]
    return {"domains": output, "display_mapping": DOMAIN_DISPLAY_NAMES}


@app.get("/comparison/domains", dependencies=protected)
def compare_domains():
    comparison = db.get_domain_comparison()
    return {"comparison": comparison, "total_domains_evaluated": len(comparison)}


@app.post("/evaluate/run", status_code=202, dependencies=protected)
def trigger_evaluation(req: EvalRunRequest):
    dom = _validate_domain(req.domain)
    kwargs = {"suite": req.suite, "question_limit": req.question_limit, "answer_model": req.model}
    if req.prompt_id:
        p = db.get_prompt(req.prompt_id)
        if not p:
            raise HTTPException(404, "Prompt not found")
        kwargs.update(system_prompt=p["system_prompt"], prompt_name=p["name"])
    job = _new_job("single", [dom])
    _executor.submit(_run_job, job, req.run_name, req.baseline_run_id, kwargs)
    return {"job_id": job["id"], "status": job["status"]}


@app.post("/evaluate/all", status_code=202, dependencies=protected)
def trigger_all_domain_evaluations():
    job = _new_job("all", list(DOMAINS_REGISTRY.keys()))
    _executor.submit(_run_job, job, None, None)
    return {"job_id": job["id"], "status": job["status"]}


@app.get("/jobs", dependencies=protected)
def list_jobs():
    return {"jobs": list(reversed(list(_jobs.values())))[:20]}


@app.get("/jobs/{job_id}", dependencies=protected)
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/runs", dependencies=protected)
def list_runs(domain: Optional[str] = None, limit: int = 50):
    limit = max(1, min(limit, 500))
    runs = db.get_runs_by_domain(domain=domain.lower().strip(), limit=limit) if domain else db.get_runs(limit=limit)
    return {"total": len(runs), "runs": runs}


@app.get("/runs/{run_id}", dependencies=protected)
def get_run_details(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {"run": run, "results": db.get_results_for_run(run_id)}


@app.get("/runs/{run_id}/export", dependencies=protected)
def export_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {"metadata": run, "export_timestamp": run.get("timestamp"),
            "question_evaluations": db.get_results_for_run(run_id)}


@app.get("/runs/{run_id}/baselines", dependencies=protected)
def comparable_baselines(run_id: str):
    """Runs that may legitimately serve as drift baseline: same domain, same scorer, real (not simulated)."""
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {"baselines": [r for r in db.get_runs_by_domain(run["domain"], limit=100)
                          if r["id"] != run_id and not r.get("is_simulated") and r.get("scorer") == run.get("scorer")]}


@app.get("/runs/{run_id}/drift", dependencies=protected)
def get_run_drift(run_id: str, baseline_id: Optional[str] = None):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    target_baseline = baseline_id
    if not target_baseline:
        prev = db.get_latest_run_for_domain(domain=run["domain"], exclude_id=run_id, scorer=run.get("scorer"))
        if not prev:
            raise HTTPException(404, "No prior comparable baseline run (same domain and scorer) available")
        target_baseline = prev["id"]
    else:
        base = db.get_run(target_baseline)
        if not base:
            raise HTTPException(404, "Baseline run not found")
        if base.get("scorer") != run.get("scorer"):
            raise HTTPException(400, f"Scorer mismatch: baseline '{base.get('scorer')}' vs current '{run.get('scorer')}'")

    detector = DriftDetector(p_value_threshold=settings.DRIFT_P_VALUE_THRESHOLD)
    report = detector.evaluate_run_drift(db.get_results_for_run(target_baseline), db.get_results_for_run(run_id))
    return {"baseline_run_id": target_baseline, "current_run_id": run_id,
            "domain": run["domain"], "drift_report": report}


@app.post("/rag/query", dependencies=protected)
def live_rag_query(req: LiveQueryRequest):
    """Live RAG query on a domain with real-time faithfulness/relevance scoring."""
    dom_key = _validate_domain(req.domain)
    cfg = DOMAINS_REGISTRY[dom_key]
    runner = EvaluationRunner(domain=dom_key)
    runner.ensure_indexed()

    try:
        rag_out = runner.rag_pipeline.query(question=req.question, top_k=req.top_k)
        ctx_texts = [c["text"] for c in rag_out["contexts"]]
        faith = FaithfulnessEvaluator(runner.judge_client, cfg.faithfulness_threshold).evaluate(rag_out["answer"], ctx_texts)
        rel = RelevanceEvaluator(runner.judge_client, cfg.relevance_threshold).evaluate(req.question, rag_out["answer"])
    except Exception as e:
        raise HTTPException(502, f"LLM provider error: {e}")

    return {
        "question": req.question, "domain": dom_key, "domain_name": cfg.name,
        "safeguard_notice": cfg.safeguard_notice, "answer": rag_out["answer"],
        "retrieved_contexts": rag_out["contexts"], "faithfulness": faith, "relevance": rel,
        "latency_ms": rag_out["total_latency_ms"], "estimated_cost": rag_out["estimated_cost"],
        "is_mock": bool(runner.llm_client.is_mock or runner.judge_client.is_mock),
    }


@app.post("/domains/{domain}/documents", dependencies=protected)
async def upload_documents(domain: str, files: List[UploadFile] = File(...)):
    dom = _validate_domain(domain)
    target_dir = settings.DATA_DIR / dom / "documents"
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = Path(f.filename or "").name  # strip any path components
        if Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
            raise HTTPException(400, f"Unsupported file type: {name!r}. Allowed: {sorted(ALLOWED_UPLOAD_EXT)}")
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{name} exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        (target_dir / name).write_bytes(data)
        saved.append(name)
    chunks = EvaluationRunner(domain=dom).ingest_domain_data()
    return {"domain": dom, "saved": saved, "indexed_chunks": chunks}


# ---------------------------------------------------------------- prompt library
class PromptIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    system_prompt: str = Field(..., min_length=10, max_length=4000)


@app.get("/prompts", dependencies=protected)
def list_prompts():
    return {"prompts": db.list_prompts()}


@app.post("/prompts", status_code=201, dependencies=protected)
def create_prompt(body: PromptIn):
    try:
        return db.create_prompt(body.name, body.system_prompt)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/prompts/{prompt_id}", dependencies=protected)
def update_prompt(prompt_id: str, body: PromptIn):
    try:
        updated = db.update_prompt(prompt_id, body.name, body.system_prompt)
    except ValueError as e:
        raise HTTPException(409, str(e))
    if not updated:
        raise HTTPException(404, "Prompt not found")
    return updated


@app.delete("/prompts/{prompt_id}", dependencies=protected)
def delete_prompt(prompt_id: str):
    p = db.get_prompt(prompt_id)
    if not p:
        raise HTTPException(404, "Prompt not found")
    if p["is_default"]:
        raise HTTPException(400, "The default prompt can't be deleted")
    db.delete_prompt(prompt_id)
    return {"deleted": True}


# ---------------------------------------------------------------- test cases (built-in + custom)
class QuestionIn(BaseModel):
    domain: str
    kind: Literal["standard", "out_of_scope", "injection", "injection_hybrid"] = "standard"
    question: str = Field(..., min_length=5, max_length=1000)
    ground_truth: str = Field(..., min_length=1, max_length=2000)
    expected_keywords: List[str] = Field(default_factory=list, max_length=6)
    must_not_contain: List[str] = Field(default_factory=list, max_length=4)


def _check_question(q: QuestionIn) -> List[str]:
    """Raises on contradictions; returns non-fatal warnings."""
    q.domain = _validate_domain(q.domain)
    warnings: List[str] = []
    if any(len(k) > 120 or not k.strip() for k in q.expected_keywords + q.must_not_contain):
        raise HTTPException(422, "Keywords must be 1-120 characters")
    if q.kind in ("injection", "injection_hybrid"):
        if not q.must_not_contain:
            raise HTTPException(422, "Injection tests need at least one must_not_contain token (the canary)")
        for c in q.must_not_contain:
            if c.lower() not in q.question.lower():
                raise HTTPException(422, f"Canary {c!r} must appear in the question text")
    if q.kind in ("standard", "injection_hybrid"):
        if not q.expected_keywords:
            warnings.append("No expected keywords: retrieval hit rate can't be measured for this question.")
        missing = keywords_missing(q.domain, q.expected_keywords)
        if missing:
            warnings.append(f"These keywords don't appear in the {q.domain} documents, so they can never score a hit: {', '.join(missing)}")
    return warnings


@app.get("/questions", dependencies=protected)
def list_questions(domain: Optional[str] = None, kind: Optional[str] = None, source: Optional[str] = None):
    if domain:
        domain = _validate_domain(domain)
    domains = [domain] if domain else list(DOMAINS_REGISTRY.keys())
    items = []
    for d in domains:
        if source != "custom":
            items += [{**i, "domain": d} for i in load_builtin(d)]
        if source != "builtin":
            items += [{**normalize_item(c, c["kind"], "custom"), "domain": d} for c in db.list_custom_questions(domain=d)]
    if kind:
        items = [i for i in items if i["kind"] == kind]
    return {"total": len(items), "questions": items}


@app.post("/questions", status_code=201, dependencies=protected)
def create_question(body: QuestionIn):
    warnings = _check_question(body)
    return {"question": db.create_custom_question(body.model_dump()), "warnings": warnings}


@app.put("/questions/{qid}", dependencies=protected)
def update_question(qid: str, body: QuestionIn):
    warnings = _check_question(body)
    updated = db.update_custom_question(qid, body.model_dump())
    if not updated:
        raise HTTPException(404, "Custom question not found (built-in questions are read-only)")
    return {"question": updated, "warnings": warnings}


@app.delete("/questions/{qid}", dependencies=protected)
def delete_question(qid: str):
    if not db.delete_custom_question(qid):
        raise HTTPException(404, "Custom question not found (built-in questions are read-only)")
    return {"deleted": True}


class QuestionImport(BaseModel):
    items: List[QuestionIn] = Field(..., min_length=1, max_length=200)


@app.post("/questions/import", dependencies=protected)
def import_questions(body: QuestionImport):
    created, errors = 0, []
    for i, item in enumerate(body.items):
        try:
            _check_question(item)
            db.create_custom_question(item.model_dump())
            created += 1
        except HTTPException as e:
            errors.append({"index": i, "error": e.detail})
    return {"created": created, "errors": errors}


# ---------------------------------------------------------------- model list (OpenRouter free models)
_models_cache: dict = {"at": 0.0, "data": []}


@app.get("/models/free", dependencies=protected)
def free_models():
    """Free text models currently listed by OpenRouter (cached 10 min). Empty if the provider isn't OpenRouter."""
    if settings.LLM_PROVIDER != "openrouter":
        return {"models": [], "provider": settings.LLM_PROVIDER}
    if time.time() - _models_cache["at"] > 600 or not _models_cache["data"]:
        try:
            r = requests.get(f"{settings.OPENROUTER_BASE_URL}/models", timeout=20)
            r.raise_for_status()
            _models_cache["data"] = sorted(
                [{"id": m["id"], "name": m.get("name", m["id"]), "context_length": m.get("context_length")}
                 for m in r.json()["data"]
                 if m.get("pricing", {}).get("prompt") == "0" and m.get("pricing", {}).get("completion") == "0"
                 and "text" in m.get("architecture", {}).get("output_modalities", [])],
                key=lambda m: -(m["context_length"] or 0))
            _models_cache["at"] = time.time()
        except Exception as e:
            raise HTTPException(502, f"Could not load the OpenRouter model list: {e}")
    return {"models": _models_cache["data"], "provider": "openrouter",
            "answer_model": settings.OPENROUTER_MODEL, "judge_model": settings.OPENROUTER_JUDGE_MODEL}


# ---------------------------------------------------------------- experiments (prompt A/B and model comparison)
class VariantIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    prompt_id: Optional[str] = None
    model: Optional[str] = Field(default=None, max_length=120)


class ExperimentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: Literal["prompt", "model"]
    domain: str
    suite: Literal["standard", "adversarial", "all"] = "standard"
    question_limit: int = Field(default=8, ge=1, le=60)
    variants: List[VariantIn] = Field(..., min_length=2, max_length=5)
    prompt_id: Optional[str] = Field(default=None, description="Shared prompt for model experiments (default prompt if omitted)")


def _run_experiment_job(job: dict, exp: dict):
    job["status"] = "running"
    db.update_experiment_status(exp["id"], "running")
    try:
        for v in exp["variants"]:
            job["progress"].update(domain=v["label"], current=0, total=0)
            try:
                runner = EvaluationRunner(
                    domain=exp["domain"], run_name=f"{exp['name']} · {v['label']}",
                    system_prompt=v["system_prompt"], prompt_name=v["prompt_name"], answer_model=v.get("model"),
                    suite=exp["suite"], question_limit=exp["question_limit"],
                    experiment_id=exp["id"], variant_label=v["label"])
                out = runner.run_evaluation(
                    auto_compare_baseline=False,
                    progress=lambda i, n: job["progress"].update(current=i, total=n))
                job["results"].append({"domain": v["label"], "status": "SUCCESS", "run": out["run"],
                                       "skipped": out["skipped"]})
            except Exception as e:
                job["results"].append({"domain": v["label"], "status": "FAILED", "error": str(e)})
            job["progress"]["domains_done"] += 1
        ok = [r for r in job["results"] if r["status"] == "SUCCESS"]
        job["status"] = "done" if ok else "failed"
        if not ok:
            job["error"] = job["results"][0]["error"]
        db.update_experiment_status(exp["id"], "done" if ok else "failed", job["error"])
    except Exception as e:
        job["status"], job["error"] = "failed", str(e)
        db.update_experiment_status(exp["id"], "failed", str(e))
    finally:
        job["finished_at"] = utcnow_iso()


@app.post("/experiments", status_code=202, dependencies=protected)
def create_experiment(req: ExperimentRequest):
    dom = _validate_domain(req.domain)
    labels = [v.label.strip() for v in req.variants]
    if len(set(labels)) != len(labels):
        raise HTTPException(422, "Variant labels must be unique")

    def resolve(prompt_id: Optional[str]) -> dict:
        p = db.get_prompt(prompt_id) if prompt_id else next((x for x in db.list_prompts() if x["is_default"]), None)
        if not p:
            raise HTTPException(404, f"Prompt {prompt_id!r} not found")
        return p

    variants = []
    if req.kind == "prompt":
        for v in req.variants:
            if not v.prompt_id:
                raise HTTPException(422, f"Variant {v.label!r} needs a prompt")
            p = resolve(v.prompt_id)
            variants.append({"label": v.label.strip(), "prompt_id": p["id"], "prompt_name": p["name"],
                             "system_prompt": p["system_prompt"], "model": None})
    else:
        if settings.LLM_PROVIDER != "openrouter":
            raise HTTPException(400, "Model comparison needs LLM_PROVIDER=openrouter")
        p = resolve(req.prompt_id)
        for v in req.variants:
            if not v.model:
                raise HTTPException(422, f"Variant {v.label!r} needs a model")
            variants.append({"label": v.label.strip(), "prompt_id": p["id"], "prompt_name": p["name"],
                             "system_prompt": p["system_prompt"], "model": v.model})

    exp_id = db.create_experiment({"name": req.name, "kind": req.kind, "domain": dom, "suite": req.suite,
                                   "question_limit": req.question_limit, "variants": variants})
    exp = db.get_experiment(exp_id)
    job = _new_job("experiment", [v["label"] for v in variants])
    _executor.submit(_run_experiment_job, job, exp)
    return {"experiment_id": exp_id, "job_id": job["id"]}


@app.get("/experiments", dependencies=protected)
def list_experiments():
    return {"experiments": db.list_experiments()}


@app.get("/experiments/{exp_id}", dependencies=protected)
def get_experiment(exp_id: str):
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    runs = db.get_runs_for_experiment(exp_id)
    by_q: "OrderedDict[str, dict]" = OrderedDict()
    for run in runs:
        for r in db.get_results_for_run(run["id"]):
            q = by_q.setdefault(r["question_id"], {"question_id": r["question_id"], "question": r["question"],
                                                   "ground_truth": r["ground_truth"], "kind": r.get("kind") or "standard",
                                                   "answers": {}})
            q["answers"][run["id"]] = {k: r.get(k) for k in (
                "generated_answer", "faithfulness_score", "relevance_score", "hit_rate",
                "safety_pass", "safety_reason", "latency_ms")}
    return {"experiment": exp, "runs": runs, "questions": list(by_q.values())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
