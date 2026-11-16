import sys
import argparse
from pathlib import Path

# Set UTF-8 encoding for Windows console compatibility
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evalguard.runner import EvaluationRunner
from evalguard.domains import DOMAINS_REGISTRY, DOMAIN_DISPLAY_NAMES

def run_single_domain(domain_key: str, run_name: str = None, baseline_id: str = None):
    cfg = DOMAINS_REGISTRY.get(domain_key)
    dom_title = cfg.name if cfg else domain_key.upper()

    print("\n==========================================")
    print(f"[EvalGuard AI] - Running Domain Evaluation: {dom_title}")
    print("==========================================")
    print(f"* Domain Key:  {domain_key}")
    print(f"* Run Label:   {run_name or 'Auto-generated'}")
    if cfg and cfg.safeguard_notice:
        print(f"* Safeguard:   {cfg.safeguard_notice}")
    print("------------------------------------------\n")

    runner = EvaluationRunner(domain=domain_key, run_name=run_name)
    output = runner.run_evaluation(baseline_run_id=baseline_id)

    run = output["run"]
    print("\n[SUCCESS] Domain Evaluation Completed!")
    print("------------------------------------------")
    print(f"* Run ID:           {run['id']}")
    print(f"* Total Questions:  {run['total_questions']}")
    print(f"* Indexed Chunks:   {output['indexed_chunks']}")
    print(f"* Avg Faithfulness: {run['avg_faithfulness']:.2%}")
    print(f"* Avg Relevance:    {run['avg_relevance']:.2%}")
    print(f"* Retrieval Hit:    {run['avg_retrieval_hit_rate']:.2%}")
    print(f"* Retrieval MRR:    {run['avg_mrr']:.3f}")
    print(f"* Avg Latency:      {run['avg_latency_ms']:.1f} ms")
    print(f"* Total Cost:       ${run['total_cost']:.6f}")
    print("------------------------------------------")

    drift = output.get("drift_report")
    if drift:
        status = drift["overall_status"]
        icon = "[ALERT]" if status == "DRIFT_DETECTED" else "[OK]"
        print(f"\n{icon} Drift Report vs Baseline:")
        print(f"* Status: {status}")
        print(f"* Recommendation: {drift['recommendation']}")
        for m_name, m_info in drift.get("metrics", {}).items():
            print(f"  - {m_name}: KS-stat={m_info['ks_statistic']:.3f}, p-val={m_info['p_value']:.4f}, drift={m_info['drift_detected']}")
    else:
        print("\n[INFO] No prior baseline run found for drift comparison in this domain. This run will serve as reference.")

    return run

def main():
    parser = argparse.ArgumentParser(description="EvalGuard AI - Multi-Domain Evaluation Runner")
    parser.add_argument(
        "--domain",
        type=str,
        default="education",
        choices=list(DOMAINS_REGISTRY.keys()),
        help=f"Target domain to evaluate: {', '.join(DOMAINS_REGISTRY.keys())}"
    )
    parser.add_argument(
        "--all-domains",
        action="store_true",
        help="Run benchmarks sequentially across all 8 supported domains"
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Optional name label for this evaluation run"
    )
    parser.add_argument(
        "--baseline-id",
        type=str,
        default=None,
        help="Specific run ID to use as drift baseline"
    )

    args = parser.parse_args()

    if args.all_domains:
        print("\n========================================================")
        print("🛡️  EvalGuard AI: Multi-Domain Batch Benchmark Suite")
        print("========================================================")
        summary = []
        for dom in DOMAINS_REGISTRY.keys():
            res = run_single_domain(domain_key=dom)
            summary.append(res)
        print("\n========================================================")
        print("📊 Batch Evaluation Complete across all 8 domains!")
        print("========================================================")
        for s in summary:
            print(f"• {s['domain'].upper():<20} | Faithfulness: {s['avg_faithfulness']:.2%} | Relevance: {s['avg_relevance']:.2%} | Latency: {s['avg_latency_ms']:.1f}ms")
    else:
        run_single_domain(domain_key=args.domain, run_name=args.run_name, baseline_id=args.baseline_id)

if __name__ == "__main__":
    main()
