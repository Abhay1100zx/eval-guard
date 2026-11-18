"""Scheduled evaluation.

Every `hours`, run ONE domain on a small sample. The domain is the one whose newest real (AI-judged) score is the
oldest, and a domain that never had one always goes first. Running one domain per tick keeps the free daily quota from
being burned at once, and it steadily fills in domains that still have no real scores before it starts refreshing the
others (which is when drift alerts become possible).

State lives in the database (table `kv`), so a restart neither skips a run nor repeats one.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("evalguard.scheduler")

LAST_RUN_KEY = "schedule.last_run_at"
LAST_RESULT_KEY = "schedule.last_result"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_real(run: Dict[str, Any]) -> bool:
    """An AI-judged run of the normal benchmark: not mock/heuristic scored, not simulated, not an experiment variant."""
    return not run.get("is_simulated") and not run.get("experiment_id") and "llm:" in (run.get("scorer") or "")


def pick_domain(db, domains: List[str]) -> str:
    """The domain whose newest real run is oldest. Domains with none sort first; ties keep the order given."""
    newest: Dict[str, str] = {}
    for r in db.get_runs(limit=1000):
        if r["domain"] in domains and is_real(r):
            newest[r["domain"]] = max(newest.get(r["domain"], ""), r["timestamp"])
    return min(domains, key=lambda d: newest.get(d, ""))


def tick(db, *, hours: float, questions: int, domains: List[str],
         run_domain: Callable[[str, int], Dict[str, Any]], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Run the next domain if one is due. `run_domain(domain, questions)` returns a job-result dict
    ({"status", "error", "run", "drift_report"}). Returns what happened, or None when nothing was due."""
    now = time.time() if now is None else now
    if hours <= 0 or not domains:
        return None
    last = db.kv_get(LAST_RUN_KEY)
    if last and now - float(last) < hours * 3600:
        return None
    # Stamp first: a crash or restart during the run must not trigger an immediate second run.
    # A failed run (quota used up, provider down) therefore waits for the next interval too, instead of retrying and
    # spending more of the free quota.
    db.kv_set(LAST_RUN_KEY, str(now))
    domain = pick_domain(db, domains)
    try:
        out = run_domain(domain, questions)
    except Exception as e:
        out = {"status": "FAILED", "error": str(e)}
    result = {"domain": domain, "at": _iso(now), "status": out.get("status"), "error": out.get("error"),
              "run_id": (out.get("run") or {}).get("id"), "drift": (out.get("drift_report") or {}).get("overall_status")}
    db.kv_set(LAST_RESULT_KEY, json.dumps(result))
    return result


def status(db, *, hours: float, questions: int, domains: List[str], now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    last = db.kv_get(LAST_RUN_KEY)
    due = None if hours <= 0 else (float(last) + hours * 3600 if last else now)
    return {
        "enabled": hours > 0, "hours": hours, "questions": questions,
        "next_domain": pick_domain(db, domains) if hours > 0 and domains else None,
        "last_run_at": _iso(float(last)) if last else None,
        "next_due_at": _iso(max(due, now)) if due is not None else None,
        "last_result": json.loads(db.kv_get(LAST_RESULT_KEY) or "null"),
    }


def run_forever(stop: threading.Event, tick_once: Callable[[], Any], *, first_delay: float = 30, every: float = 60) -> None:
    """Call tick_once() every minute until `stop` is set. An error in one tick is logged and the loop carries on."""
    if stop.wait(first_delay):
        return
    while True:
        try:
            tick_once()
        except Exception:
            log.exception("scheduled evaluation failed")
        if stop.wait(every):
            return
