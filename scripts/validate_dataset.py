"""Validate benchmark datasets against their source documents. Stdlib only.

    py -I scripts/validate_dataset.py            # all domains
    py -I scripts/validate_dataset.py hr legal   # some domains

Standard questions (data/<domain>/test_questions.json):
    id, question, ground_truth, expected_keywords (2-4, each must appear in the domain's documents)
Adversarial questions (data/<domain>/adversarial_questions.json):
    kind = out_of_scope | injection | injection_hybrid
    out_of_scope     : answerable=false, ground_truth says the documents don't specify it
    injection        : answerable=false, must_not_contain (canary) must appear in the question text
    injection_hybrid : answerable=true, expected_keywords (in documents) + must_not_contain canary in question
Exit code is non-zero if anything fails.
"""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KINDS = {"out_of_scope", "injection", "injection_hybrid"}


def norm(t: str) -> str:  # must match RetrievalEvaluator._norm
    return re.sub(r"[^\w$%.]+", " ", t.lower()).strip()


def check_domain(domain: str) -> list:
    errs = []
    ddir = DATA / domain
    docs = " ".join(norm(p.read_text(encoding="utf-8", errors="replace")) for p in (ddir / "documents").rglob("*") if p.suffix.lower() in {".txt", ".md"})
    seen_ids, seen_q = set(), set()

    def common(item, where):
        for f in ("id", "question", "ground_truth"):
            if not str(item.get(f, "")).strip():
                errs.append(f"{where}: missing {f}")
        if item.get("id") in seen_ids:
            errs.append(f"{where}: duplicate id {item.get('id')}")
        seen_ids.add(item.get("id"))
        q = norm(item.get("question", ""))
        if q in seen_q:
            errs.append(f"{where}: duplicate question")
        seen_q.add(q)

    def keywords(item, where):
        kws = item.get("expected_keywords", [])
        if not (2 <= len(kws) <= 4):
            errs.append(f"{where}: needs 2-4 expected_keywords, has {len(kws)}")
        for kw in kws:
            if norm(kw) not in docs:
                errs.append(f"{where}: keyword {kw!r} not found in documents")

    std = ddir / "test_questions.json"
    n_std = 0
    if std.exists():
        for i, it in enumerate(json.loads(std.read_text(encoding="utf-8"))):
            w = f"{domain}/test_questions[{i}] {it.get('id')}"
            common(it, w)
            keywords(it, w)
            n_std += 1
    adv = ddir / "adversarial_questions.json"
    n_adv = 0
    if adv.exists():
        for i, it in enumerate(json.loads(adv.read_text(encoding="utf-8"))):
            w = f"{domain}/adversarial[{i}] {it.get('id')}"
            common(it, w)
            kind = it.get("kind")
            if kind not in KINDS:
                errs.append(f"{w}: kind must be one of {sorted(KINDS)}")
                continue
            if kind == "out_of_scope":
                if it.get("answerable") is not False:
                    errs.append(f"{w}: out_of_scope must have answerable=false")
                gt = it.get("ground_truth", "").lower()
                if not re.search(r"not (specif|mention|provid|contain|cover|state|address|includ)|no information|does not", gt):
                    errs.append(f"{w}: ground_truth should say the documents do not specify this")
                # the asked-about fact must really be absent: none of its distinctive numbers may be in docs
                nums = set(re.findall(r"\d[\d.,]*", it.get("question", "")))
                if nums and all(n.strip(".,") and norm(n) in docs for n in nums):
                    errs.append(f"{w}: every number in the question appears in the documents - is it really out of scope?")
            else:
                canary = it.get("must_not_contain", [])
                if not canary:
                    errs.append(f"{w}: injection needs must_not_contain")
                for c in canary:
                    if c.lower() not in it.get("question", "").lower():
                        errs.append(f"{w}: canary {c!r} must appear in the question text")
                    if norm(c) in docs:
                        errs.append(f"{w}: canary {c!r} appears in the documents (would false-fail)")
                if kind == "injection":
                    if it.get("answerable") is not False:
                        errs.append(f"{w}: injection must have answerable=false")
                else:
                    if it.get("answerable") is not True:
                        errs.append(f"{w}: injection_hybrid must have answerable=true")
                    keywords(it, w)
            n_adv += 1
    print(f"{domain:20s} standard={n_std:3d} adversarial={n_adv:2d} errors={len(errs)}")
    return errs


def main():
    domains = sys.argv[1:] or sorted(p.name for p in DATA.iterdir() if (p / "documents").is_dir())
    all_errs = []
    for d in domains:
        all_errs += check_domain(d)
    for e in all_errs[:60]:
        print("  ERROR", e)
    if len(all_errs) > 60:
        print(f"  ... and {len(all_errs) - 60} more")
    sys.exit(1 if all_errs else 0)


if __name__ == "__main__":
    main()
