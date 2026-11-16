"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useFetch } from "@/lib/api";
import type { ExperimentDetail, Job, Run } from "@/lib/types";
import { Badge, Card, ErrorBox, LiveDot, PageHeader, Spinner, domainLabel, fmtDate, pct, scoreTone, statusTone, useDomains } from "@/components/ui";

const METRICS: { key: keyof Run; label: string; higherIsBetter: boolean; fmt: (v: number) => string }[] = [
  { key: "avg_faithfulness", label: "Faithfulness", higherIsBetter: true, fmt: (v) => pct(v) },
  { key: "avg_relevance", label: "Relevance", higherIsBetter: true, fmt: (v) => pct(v) },
  { key: "avg_retrieval_hit_rate", label: "Hit rate", higherIsBetter: true, fmt: (v) => pct(v) },
  { key: "avg_safety", label: "Safety", higherIsBetter: true, fmt: (v) => pct(v) },
  { key: "avg_latency_ms", label: "Latency", higherIsBetter: false, fmt: (v) => `${v.toFixed(0)} ms` },
];

function bestIds(runs: Run[], key: keyof Run, higherIsBetter: boolean): Set<string> {
  const vals = runs.map((r) => [r.id, r[key] as number | null] as const).filter(([, v]) => v != null) as [string, number][];
  if (vals.length < 2) return new Set();
  const best = (higherIsBetter ? Math.max : Math.min)(...vals.map(([, v]) => v));
  // values within 2% of the best count as tied with it; if everyone is tied there is no winner to mark
  const tied = (v: number) => Math.abs(v - best) <= Math.abs(best) * 0.02 + 1e-9;
  const winners = vals.filter(([, v]) => tied(v));
  return winners.length === vals.length ? new Set() : new Set(winners.map(([id]) => id));
}

export default function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = useSearchParams().get("job");
  const { byKey } = useDomains();
  const { data, loading, error, reload } = useFetch<ExperimentDetail>(`/experiments/${id}`);
  const job = useFetch<Job>(jobId ? `/jobs/${jobId}` : null);
  const [onlyDiffs, setOnlyDiffs] = useState(false);

  const active = data?.experiment.status === "queued" || data?.experiment.status === "running";
  const reloadJob = job.reload;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => { reload(); if (jobId) reloadJob(); }, 4000);
    return () => clearInterval(t);
  }, [active, reload, reloadJob, jobId]);

  const runs = useMemo(() => data?.runs ?? [], [data]);
  const questions = useMemo(() => data?.questions ?? [], [data]);
  const bestPer = useMemo(() => Object.fromEntries(METRICS.map((m) => [m.key, bestIds(runs, m.key, m.higherIsBetter)])), [runs]);

  // overall = mean of quality metrics that exist (faithfulness, relevance, safety when measured)
  const overall = useMemo(() => runs.map((r) => {
    const parts = [r.avg_faithfulness, r.avg_relevance, r.avg_safety].filter((v): v is number => v != null);
    return { run: r, score: parts.reduce((a, b) => a + b, 0) / parts.length };
  }).sort((a, b) => b.score - a.score), [runs]);

  const differs = (q: ExperimentDetail["questions"][number]) => {
    const a = Object.values(q.answers);
    if (a.length < 2) return false;
    const spread = (f: (x: (typeof a)[number]) => number) => Math.max(...a.map(f)) - Math.min(...a.map(f));
    return spread((x) => x.faithfulness_score) > 0.2 || spread((x) => x.relevance_score) > 0.2 || new Set(a.map((x) => x.safety_pass)).size > 1;
  };
  const shown = onlyDiffs ? questions.filter(differs) : questions;

  if (loading && !data) return <Spinner />;
  if (error || !data) return <ErrorBox message={error ?? "Experiment not found"} onRetry={reload} />;
  const { experiment: exp } = data;
  const label = (r: Run) => r.variant_label ?? r.run_name;
  const p = job.data?.progress;
  const top = overall[0];
  const margin = overall.length > 1 ? top.score - overall[1].score : 0;
  const nQ = Math.min(...runs.map((r) => r.total_questions), Infinity);

  return (
    <>
      <Link href="/experiments" className="mb-3 inline-block text-sm text-muted hover:text-foreground">← All experiments</Link>
      <PageHeader
        title={exp.name}
        subtitle={`${exp.kind === "prompt" ? "Prompt" : "Model"} comparison · ${domainLabel(byKey, exp.domain)} · ${exp.suite} questions${exp.question_limit ? ` (${exp.question_limit} per variant)` : ""} · ${fmtDate(exp.created_at)}`}
        actions={<Badge tone={statusTone(exp.status)}>{active && <LiveDot />}{exp.status}</Badge>}
      />

      {active && (
        <div role="status" className="glass rise mb-6 p-4 text-sm">
          <div className="font-medium">Running variant {Math.min((p?.domains_done ?? runs.length) + 1, exp.variants.length)} of {exp.variants.length}{p?.domain ? `: ${p.domain}` : ""}</div>
          {p && p.total > 0 && <div className="mt-1 text-muted">Question {Math.min(p.current + 1, p.total)} of {p.total}</div>}
          <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div className="progress-fill h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(4, ((((p?.domains_done ?? runs.length)) + (p && p.total ? p.current / p.total : 0)) / exp.variants.length) * 100)}%` }} />
          </div>
          <p className="mt-2 text-xs text-muted">Free models are rate-limited, so this can take several minutes. You can leave this page; results stay saved.</p>
        </div>
      )}
      {exp.status === "failed" && exp.error && <div className="mb-6"><ErrorBox message={exp.error} /></div>}

      {runs.length > 0 && (
        <>
          {runs.some((r) => r.scorer?.includes("mock")) && (
            <div role="alert" className="glass rise mb-6 p-3.5 text-sm" style={{ background: "color-mix(in srgb, var(--bad) 12%, var(--glass))" }}>
              <strong className="text-bad">Mock judge.</strong> These scores are hard-coded constants, not measurements, so no variant is genuinely better. Configure a real LLM to get meaningful results.
            </div>
          )}
          {!active && top && overall.length > 1 && (
            <div className="glass rise mb-6 p-4 text-sm" style={{ background: `color-mix(in srgb, var(${margin < 0.02 ? "--warn" : "--good"}) 10%, var(--glass))` }}>
              {margin < 0.02 ? (<><strong>No clear winner:</strong> {label(top.run)} and {label(overall[1].run)} are within 2 points of each other ({pct(top.score)} vs {pct(overall[1].score)}).</>)
                : (<><strong>{label(top.run)}</strong> scored highest overall ({pct(top.score)}), {(margin * 100).toFixed(1)} points ahead of {label(overall[1].run)}.</>)}
              {nQ < 20 && <span className="text-muted"> With {nQ} questions per variant, gaps under about 10 points are likely noise. Re-run with more questions before acting on a small difference.</span>}
            </div>
          )}

          <Card title="Summary">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Variant</th>
                    <th className="pr-4 font-medium">{exp.kind === "prompt" ? "Prompt" : "Model"}</th>
                    {METRICS.map((m) => <th key={m.key} className="pr-4 text-right font-medium">{m.label}</th>)}
                    <th className="text-right font-medium">Questions</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-2.5 pr-4 font-medium"><Link href={`/runs/${r.id}`} className="text-accent hover:underline">{label(r)}</Link></td>
                      <td className="max-w-48 truncate pr-4 text-muted" title={exp.kind === "prompt" ? r.prompt_name ?? "" : r.model_name ?? ""}>{exp.kind === "prompt" ? r.prompt_name : r.model_name}</td>
                      {METRICS.map((m) => {
                        const v = r[m.key] as number | null;
                        const win = bestPer[m.key]?.has(r.id);
                        return (
                          <td key={m.key} className={`pr-4 text-right tabular-nums ${win ? "font-semibold text-good" : ""}`}>
                            {v == null ? <span className="text-muted">—</span> : m.fmt(v)}{win ? " ▲" : ""}
                          </td>
                        );
                      })}
                      <td className="text-right tabular-nums">{r.total_questions}{r.status === "PARTIAL" ? <Badge tone="warn" title="Some questions failed and were skipped">partial</Badge> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-muted">▲ marks the best value in a column (lowest for latency). Judge: {runs[0]?.scorer ?? "unknown"}. Free models can vary run to run, so treat small gaps with care.</p>
          </Card>

          <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Question by question ({shown.length})</h2>
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={onlyDiffs} onChange={(e) => setOnlyDiffs(e.target.checked)} className="size-4 accent-[var(--accent)]" />
              Only where variants differ
            </label>
          </div>
          {shown.length === 0 && <p className="text-sm text-muted">No questions where the variants differ meaningfully.</p>}
          <div className="space-y-2">
            {shown.map((q) => (
              <details key={q.question_id} className="glass group">
                <summary className="flex cursor-pointer flex-wrap items-center gap-3 p-4">
                  <span className="min-w-0 flex-1 font-medium">{q.question}</span>
                  {q.kind !== "standard" && <Badge tone="accent">{q.kind.replace("_", " ")}</Badge>}
                  {runs.map((r) => {
                    const a = q.answers[r.id];
                    return a ? <Badge key={r.id} tone={scoreTone(Math.min(a.faithfulness_score, a.relevance_score), 0.75)}>{label(r)} {a.faithfulness_score.toFixed(2)}/{a.relevance_score.toFixed(2)}</Badge> : null;
                  })}
                </summary>
                <div className="space-y-4 border-t border-border p-4 text-sm">
                  <div><div className="mb-1 text-xs font-medium text-muted">Expected (ground truth)</div><p>{q.ground_truth}</p></div>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {runs.map((r) => {
                      const a = q.answers[r.id];
                      return (
                        <div key={r.id} className="glass-inset rounded-2xl p-3.5">
                          <div className="mb-2 flex flex-wrap items-center gap-1.5">
                            <span className="font-semibold">{label(r)}</span>
                            {a && <><Badge tone={scoreTone(a.faithfulness_score)}>faith {a.faithfulness_score.toFixed(2)}</Badge><Badge tone={scoreTone(a.relevance_score)}>rel {a.relevance_score.toFixed(2)}</Badge></>}
                            {a?.safety_pass != null && <Badge tone={a.safety_pass ? "good" : "bad"}>{a.safety_pass ? "safe" : "unsafe"}</Badge>}
                          </div>
                          {a ? <p className="whitespace-pre-wrap">{a.generated_answer}</p> : <p className="text-muted">Not answered (skipped after errors).</p>}
                          {a?.safety_reason && <p className="mt-2 text-xs text-muted">{a.safety_reason}</p>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </details>
            ))}
          </div>
        </>
      )}
      {!active && runs.length === 0 && exp.status !== "failed" && <p className="text-sm text-muted">No results were saved for this experiment.</p>}
    </>
  );
}
