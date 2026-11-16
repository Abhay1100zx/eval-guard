"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useFetch } from "@/lib/api";
import type { QResult, Run } from "@/lib/types";
import { Badge, Button, ErrorBox, PageHeader, ScorerBadge, Spinner, Stat, fmtDate, pct, scoreTone, useDomains } from "@/components/ui";

const csvCell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;

function exportCsv(run: Run, results: QResult[]) {
  const cols = ["question_id", "kind", "question", "ground_truth", "generated_answer", "faithfulness_score", "faithfulness_reason",
    "relevance_score", "relevance_reason", "hit_rate", "mrr", "safety_pass", "safety_reason", "latency_ms", "cost"] as const;
  const rows = [cols.join(","), ...results.map((r) => cols.map((c) => csvCell(r[c])).join(","))];
  const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `evalguard_${run.domain}_${run.id.slice(0, 8)}.csv` });
  a.click();
  URL.revokeObjectURL(url);
}

const KIND_LABEL: Record<string, string> = { standard: "standard", out_of_scope: "out of scope", injection: "injection", injection_hybrid: "injection + question" };

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const { byKey } = useDomains();
  const { data, loading, error, reload } = useFetch<{ run: Run; results: QResult[] }>(`/runs/${id}`);

  if (loading) return <Spinner />;
  if (error || !data) return <ErrorBox message={error ?? "Run not found"} onRetry={reload} />;
  const { run, results } = data;
  const dom = byKey[run.domain];
  const fT = dom?.faithfulness_threshold ?? 0.7;
  const rT = dom?.relevance_threshold ?? 0.7;

  return (
    <>
      <Link href="/runs" className="mb-3 inline-block text-sm text-muted hover:text-foreground">← All runs</Link>
      <PageHeader
        title={run.run_name}
        subtitle={`${dom?.icon ?? ""} ${dom?.name ?? run.domain} · ${fmtDate(run.timestamp)} · answered by ${run.model_name}`}
        actions={<Button variant="ghost" onClick={() => exportCsv(run, results)}>Export CSV</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ScorerBadge run={run} />
        {run.scorer && <span className="text-xs text-muted">scorer: {run.scorer}</span>}
        {run.suite && run.suite !== "standard" && <Badge tone="accent">{run.suite} suite</Badge>}
        {run.prompt_name && <Badge title={`prompt fingerprint ${run.prompt_hash}`}>prompt: {run.prompt_name}</Badge>}
        {run.status === "PARTIAL" && <Badge tone="warn" title="Some questions failed with LLM errors and were skipped">partial</Badge>}
        {run.experiment_id && <Link href={`/experiments/${run.experiment_id}`} className="text-xs text-accent underline">part of an experiment</Link>}
      </div>
      {dom?.safeguard_notice && <div className="glass mb-4 p-3.5 text-sm" style={{ background: "color-mix(in srgb, var(--warn) 12%, var(--glass))" }}>⚠️ {dom.safeguard_notice}</div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat delay={0} label="Faithfulness" value={pct(run.avg_faithfulness)} tone={scoreTone(run.avg_faithfulness, fT)} />
        <Stat delay={1} label="Relevance" value={pct(run.avg_relevance)} tone={scoreTone(run.avg_relevance, rT)} />
        <Stat delay={2} label="Hit rate" value={pct(run.avg_retrieval_hit_rate)} hint={run.avg_retrieval_hit_rate === null ? "not applicable" : undefined} />
        <Stat delay={3} label="MRR" value={run.avg_mrr == null ? "—" : run.avg_mrr.toFixed(3)} />
        <Stat delay={4} label="Safety" value={pct(run.avg_safety)} tone={run.avg_safety == null ? undefined : scoreTone(run.avg_safety, 0.9)} hint={run.avg_safety == null ? "standard questions only" : "adversarial checks passed"} />
        <Stat delay={5} label="Latency" value={`${run.avg_latency_ms.toFixed(0)} ms`} hint={`cost ${run.total_cost.toFixed(5)}`} />
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold">Questions ({results.length})</h2>
      <div className="space-y-2">
        {results.map((r, i) => {
          const ok = r.faithfulness_score >= fT && r.relevance_score >= rT;
          return (
            <details key={r.id} className="glass group">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4">
                <span aria-hidden>{ok ? "✅" : "⚠️"}</span>
                <span className="min-w-0 flex-1 font-medium">Q{i + 1}. {r.question}</span>
                <Badge tone={scoreTone(r.faithfulness_score, fT)}>faith {r.faithfulness_score.toFixed(2)}</Badge>
                <Badge tone={scoreTone(r.relevance_score, rT)}>rel {r.relevance_score.toFixed(2)}</Badge>
                {r.kind && r.kind !== "standard" && <Badge tone="accent">{KIND_LABEL[r.kind] ?? r.kind}</Badge>}
                {r.safety_pass != null && <Badge tone={r.safety_pass ? "good" : "bad"}>{r.safety_pass ? "safe" : "unsafe"}</Badge>}
                {r.hit_rate != null && <Badge tone={r.hit_rate ? "good" : "bad"}>{r.hit_rate ? "retrieved" : "missed"}</Badge>}
              </summary>
              <div className="space-y-4 border-t border-border p-4 text-sm">
                <div className="grid gap-4 md:grid-cols-2">
                  <div><div className="mb-1 text-xs font-medium text-muted">Expected (ground truth)</div><p>{r.ground_truth}</p></div>
                  <div><div className="mb-1 text-xs font-medium text-muted">Generated answer</div><p>{r.generated_answer}</p></div>
                </div>
                {r.safety_reason && (
                  <div className="glass-inset rounded-2xl p-3.5" style={{ background: `color-mix(in srgb, var(${r.safety_pass ? "--good" : "--bad"}) 10%, var(--glass-inset))` }}>
                    <div className="mb-1 text-xs font-medium text-muted">Safety check</div>{r.safety_reason}
                  </div>
                )}
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="glass-inset rounded-2xl p-3.5"><div className="mb-1 text-xs font-medium text-muted">Faithfulness reasoning</div>{r.faithfulness_reason}</div>
                  <div className="glass-inset rounded-2xl p-3.5"><div className="mb-1 text-xs font-medium text-muted">Relevance reasoning</div>{r.relevance_reason}</div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-medium text-muted">Retrieved context · {r.latency_ms.toFixed(0)} ms{r.mrr != null ? ` · MRR ${r.mrr}` : ""}</div>
                  <div className="space-y-2">
                    {r.retrieved_contexts.map((c, j) => (
                      <blockquote key={j} className="glass-inset rounded-2xl p-3.5">
                        <div className="mb-1 text-xs text-muted">Chunk {j + 1} · {c.metadata?.source ?? "unknown"} · similarity {c.score.toFixed(3)}</div>
                        <p className="whitespace-pre-wrap">{c.text}</p>
                      </blockquote>
                    ))}
                  </div>
                </div>
              </div>
            </details>
          );
        })}
      </div>
    </>
  );
}
