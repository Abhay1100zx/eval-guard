import sys
import uuid
import argparse
from pathlib import Path
from datetime import datetime

# Set UTF-8 encoding for Windows console compatibility
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.storage.database import DatabaseManager
from evalguard.config import utcnow_iso
from evalguard.drift.detector import DriftDetector
from evalguard.domains import DOMAINS_REGISTRY
from evalguard.runner import EvaluationRunner

def main():
    parser = argparse.ArgumentParser(description="EvalGuard AI - Drift Simulation Engine")
    parser.add_argument(
        "--domain",
        type=str,
        default="education",
        choices=list(DOMAINS_REGISTRY.keys()),
        help=f"Target domain to simulate drift: {', '.join(DOMAINS_REGISTRY.keys())}"
    )
    args = parser.parse_args()

    domain = args.domain.lower().strip()
    cfg = DOMAINS_REGISTRY.get(domain)
    dom_title = cfg.name if cfg else domain.upper()

    print("\n==========================================")
    print(f"[DRIFT SIMULATOR] - EvalGuard AI ({dom_title})")
    print("==========================================")
    print("Injecting degraded run data to simulate model drift & hallucination surge...\n")

    db = DatabaseManager()

    # Find an existing baseline run or generate one
    latest_baseline = db.get_latest_run_for_domain(domain)
    if not latest_baseline:
        print(f"[INFO] No baseline run found for domain '{domain}'. Generating baseline evaluation...")
        runner = EvaluationRunner(domain=domain)
        base_out = runner.run_evaluation()
        latest_baseline = base_out["run"]

    baseline_id = latest_baseline["id"]
    base_results = db.get_results_for_run(baseline_id)

    if not base_results:
        print(f"[INFO] No question records found for baseline run '{baseline_id}'. Generating fresh evaluation...")
        runner = EvaluationRunner(domain=domain)
        base_out = runner.run_evaluation()
        latest_baseline = base_out["run"]
        baseline_id = latest_baseline["id"]
        base_results = base_out["results"]

    print(f"* Baseline Run: {latest_baseline['run_name']} ({baseline_id[:8]}...)")
    print(f"* Baseline Faithfulness: {latest_baseline['avg_faithfulness']:.2%}")
    print(f"* Baseline Relevance:    {latest_baseline['avg_relevance']:.2%}")

    # Generate synthetic degraded results
    degraded_results = []
    for r in base_results:
        # Simulate hallucinations & poor retrieval
        deg_entry = {
            "question_id": r.get("question_id", ""),
            "question": r.get("question", ""),
            "ground_truth": r.get("ground_truth", ""),
            "retrieved_contexts": [],
            "generated_answer": "According to obsolete guidelines, requirements are waived and penalty fees apply without notice.",
            "faithfulness_score": round(max(0.1, r.get("faithfulness_score", 0.8) * 0.35), 4),
            "faithfulness_reason": "Severe hallucination: answer fabricates non-existent monetary penalties and contradictory waivers.",
            "relevance_score": round(max(0.15, r.get("relevance_score", 0.8) * 0.40), 4),
            "relevance_reason": "Answer only tangentially references the topic with incorrect information.",
            "hit_rate": 0.0,
            "mrr": 0.0,
            "latency_ms": round(r.get("latency_ms", 10.0) * 2.8, 1),
            "cost": r.get("cost", 0.0001) * 1.5
        }
        degraded_results.append(deg_entry)

    # Compute averages
    n = len(degraded_results) or 1
    avg_f = sum(x["faithfulness_score"] for x in degraded_results) / n
    avg_r = sum(x["relevance_score"] for x in degraded_results) / n
    avg_hit = sum(x["hit_rate"] for x in degraded_results) / n
    avg_mrr = sum(x["mrr"] for x in degraded_results) / n
    avg_lat = sum(x["latency_ms"] for x in degraded_results) / n
    tot_cost = sum(x["cost"] for x in degraded_results)

    sim_run_id = str(uuid.uuid4())
    sim_run_data = {
        "id": sim_run_id,
        "run_name": f"{dom_title} (Drifted Model v2 - Degraded)",
        "domain": domain,
        "timestamp": utcnow_iso(),
        "model_name": "simulated-degraded-model",
        "embedding_model": "all-MiniLM-L6-v2",
        "total_questions": len(degraded_results),
        "avg_faithfulness": round(avg_f, 4),
        "avg_relevance": round(avg_r, 4),
        "avg_retrieval_hit_rate": round(avg_hit, 4),
        "avg_mrr": round(avg_mrr, 4),
        "avg_latency_ms": round(avg_lat, 2),
        "total_cost": round(tot_cost, 6),
        "status": "COMPLETED",
        "scorer": latest_baseline.get("scorer"),
        "is_simulated": True  # excluded from auto-baseline and cross-domain comparison
    }

    db.save_run(sim_run_data, degraded_results)

    # Run Drift Detector
    detector = DriftDetector(p_value_threshold=0.05)
    drift_report = detector.evaluate_run_drift(base_results, degraded_results)
    db.save_drift_records(baseline_id, sim_run_id, drift_report)

    print(f"\n[ALERT] Degraded Run Created! Run ID: {sim_run_id}")
    print(f"* Simulated Faithfulness: {avg_f:.2%} (Dropped from {latest_baseline['avg_faithfulness']:.2%})")
    print(f"* Simulated Relevance:    {avg_r:.2%} (Dropped from {latest_baseline['avg_relevance']:.2%})")
    print(f"* Drift Status:           {drift_report['overall_status']}")
    print(f"* Alert:                  {drift_report['recommendation']}")
    print("\nOpen the Streamlit Dashboard (`streamlit run dashboard/app.py`) to inspect the Drift Detection Lab!")

if __name__ == "__main__":
    main()
