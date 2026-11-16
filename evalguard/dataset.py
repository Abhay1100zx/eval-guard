"""Benchmark question loading: built-in JSON files + custom questions stored in SQLite."""
import json
import re
from typing import Any, Dict, List, Optional

from evalguard.config import settings

STANDARD = "standard"
ADVERSARIAL_KINDS = ("out_of_scope", "injection", "injection_hybrid")
ALL_KINDS = (STANDARD,) + ADVERSARIAL_KINDS
SUITES = ("standard", "adversarial", "all")
UNANSWERABLE = ("out_of_scope", "injection")


def _norm(text: str) -> str:  # same normalisation as RetrievalEvaluator._norm
    return re.sub(r"[^\w$%.]+", " ", text.lower()).strip()


def normalize_item(raw: Dict[str, Any], kind: Optional[str] = None, source: str = "builtin") -> Dict[str, Any]:
    kind = kind or raw.get("kind") or STANDARD
    return {
        "id": raw.get("id") or raw.get("question_id"),
        "kind": kind,
        "question": raw.get("question", ""),
        "ground_truth": raw.get("ground_truth", ""),
        "expected_keywords": list(raw.get("expected_keywords") or []),
        "must_not_contain": list(raw.get("must_not_contain") or []),
        "answerable": kind not in UNANSWERABLE,
        "source": source,
    }


def _read_json(path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_builtin(domain: str) -> List[Dict[str, Any]]:
    base = settings.DATA_DIR / domain
    items = [normalize_item(r, STANDARD) for r in _read_json(base / "test_questions.json")]
    items += [normalize_item(r) for r in _read_json(base / "adversarial_questions.json")]
    return items


def load_questions(domain: str, suite: str = "standard", db=None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Built-in + custom questions for a suite; `limit` takes an evenly spaced, deterministic sample."""
    if suite not in SUITES:
        raise ValueError(f"suite must be one of {SUITES}")
    items = load_builtin(domain)
    if db is not None:
        items += [normalize_item(r, r["kind"], "custom") for r in db.list_custom_questions(domain=domain)]
    if suite == "standard":
        items = [i for i in items if i["kind"] == STANDARD]
    elif suite == "adversarial":
        items = [i for i in items if i["kind"] != STANDARD]
    if limit and 0 < limit < len(items):
        items = [items[(i * len(items)) // limit] for i in range(limit)]
    return items


def keywords_missing(domain: str, keywords: List[str]) -> List[str]:
    """Expected keywords that don't literally appear in the domain's documents (they would never score a hit)."""
    docs_dir = settings.DATA_DIR / domain / "documents"
    text = " ".join(
        _norm(p.read_text(encoding="utf-8", errors="replace"))
        for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"}
    ) if docs_dir.exists() else ""
    return [k for k in keywords if _norm(k) not in text]
