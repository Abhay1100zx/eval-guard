"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFetch } from "@/lib/api";
import type { DriftReport, QResult, Run } from "@/lib/types";
import { Badge, Card, Empty, ErrorBox, MockBanner, PageHeader, ScorerBadge, Spinner, domainLabel, fmtDate, inputCls, useDomains } from "@/components/ui";

const METRIC_LABEL: Record<string, string> = {
  faithfulness_score: "Faithfulness", relevance_score: "Relevance", hit_rate: "Hit rate", latency_ms: "Latency (ms)",
};

function bins(a: number[], b: number[], n = 8) {
  const all = [...a, ...b];
  const lo = Math.min(...all), hi = Math.max(...all);
  const w = (hi - lo) / n || 1;
  const out = Array.from({ length: n }, (_, i) => ({ range: (lo + i * w).toFixed(2), Baseline: 0, Candidate: 0 }));
  const put = (v: number, k: "Baseline" | "Candidate") => { out[Math.min(n - 1, Math.floor((v - lo) / w))][k]++; };
  a.forEach((v) => put(v, "Baseline"));
  b.forEach((v) => put(v, "Candidate"));
  return out;
}

export default function Drift() {
  const { byKey } = useDomains();
  const runsRes = useFetch<{ runs: Run[] }>("/runs?limit=200");
  const [pickedCurr, setCurrId] = useState("");
  const [pickedBase, setBaseId] = useState("");
  const [metric, setMetric] = useState("faithfulness_score");

  const runs = useMemo(() => runsRes.data?.runs ?? [], [runsRes.data]);
  const currId = pickedCurr || runs[0]?.id || "";

  const baselines = useFetch<{ baselines: Run[] }>(currId ? `/runs/${currId}/baselines` : null);
  const options = useMemo(() => baselines.data?.baselines ?? [], [baselines.data]);
  const baseId = options.some((o) => o.id === pickedBase) ? pickedBase : (options[0]?.id ?? "");

  const drift = useFetch<{ drift_report: DriftReport }>(currId && baseId ? `/runs/${currId}/drift?baseline_id=${baseId}` : null);
  const curr = useFetch<{ results: QResult[] }>(currId && baseId ? `/runs/${currId}` : null);
  const base = useFetch<{ results: QResult[] }>(currId && baseId ? `/runs/${baseId}` : null);

  const hist = useMemo(() => {
    if (!curr.data || !base.data) return [];
    const pick = (rs: QResult[]) => rs.map((r) => Number(r[metric as keyof QResult]));
    return bins(pick(base.data.results), pick(curr.data.results));
  }, [curr.data, base.data, metric]);

  if (runsRes.loading) return <Spinner />;
  if (runsRes.error) return <ErrorBox message={runsRes.error} onRetry={runsRes.reload} />;
  const currRun = runs.find((r) => r.id === currId);
  const report = drift.data?.drift_report;

  return (
    <>
      <PageHeader title="Drift lab" subtitle="Kolmogorov–Smirnov test between two runs. Only runs of the same domain scored the same way can be compared." />
      <MockBanner />
      {runs.length < 2 ? (
        <Empty title="Need at least two runs" hint="Run an evaluation twice, or use the drift simulator, to compare distributions." href="/evaluate" cta="Run an evaluation" />
      ) : (
        <>
          <Card>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="c" className="mb-1 block text-xs text-muted">Candidate (current)</label>
                <select id="c" className={inputCls} value={currId} onChange={(e) => setCurrId(e.target.value)}>
                  {runs.map((r) => <option key={r.id} value={r.id}>{domainLabel(byKey, r.domain)} · {r.run_name} · {r.id.slice(0, 6)}{r.is_simulated ? " · simulated" : ""}</option>)}
                </select>
                {currRun && <div className="mt-2"><ScorerBadge run={currRun} /></div>}
              </div>
              <div>
                <label htmlFor="b" className="mb-1 block text-xs text-muted">Baseline (reference) — same domain & scorer</label>
                <select id="b" className={inputCls} value={baseId} onChange={(e) => setBaseId(e.target.value)} disabled={!options.length}>
                  {options.length === 0 && <option value="">No comparable runs</option>}
                  {options.map((r) => <option key={r.id} value={r.id}>{r.run_name} · {fmtDate(r.timestamp)}</option>)}
                </select>
              </div>
            </div>
          </Card>

          {baselines.loading ? <Spinner /> : !options.length ? (
            <div className="mt-6"><Empty title="No comparable baseline" hint="Drift needs another run of this domain scored by the same judge. A different judge model or scorer makes the comparison meaningless, so it is blocked." /></div>
          ) : drift.loading ? <Spinner label="Running KS test…" /> : drift.error ? <div className="mt-6"><ErrorBox message={drift.error} /></div> : report && (
            <>
              <div role="status" className="glass rise mt-6 p-4" style={{ background: `color-mix(in srgb, var(${report.overall_status === "DRIFT_DETECTED" ? "--bad" : "--good"}) 12%, var(--glass))` }}>
                <div className="font-semibold">{report.overall_status === "DRIFT_DETECTED" ? "🚨 Drift detected" : "✅ Healthy"}</div>
                <p className="mt-1 text-sm">{report.recommendation}</p>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {Object.entries(report.metrics).map(([k, m]) => (
                  <button key={k} onClick={() => setMetric(k)} className={`glass btn-spring p-4 text-left ${metric === k ? "ring-2 ring-accent" : ""}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{METRIC_LABEL[k] ?? k}</span>
                      <Badge tone={m.drift_detected ? "bad" : m.severity === "WARNING" ? "warn" : "good"}>{m.drift_detected ? "drift" : m.severity === "WARNING" ? "warning" : "stable"}</Badge>
                    </div>
                    <div className="mt-2 text-2xl font-semibold tabular-nums">{m.current_mean.toFixed(3)}</div>
                    <div className={`text-xs tabular-nums ${m.mean_delta < 0 && k !== "latency_ms" ? "text-bad" : "text-muted"}`}>
                      {m.mean_delta >= 0 ? "+" : ""}{m.mean_delta.toFixed(3)} vs {m.baseline_mean.toFixed(3)}
                    </div>
                    <div className="mt-1 text-xs text-muted">KS {m.ks_statistic.toFixed(3)} · p {m.p_value.toFixed(4)}</div>
                  </button>
                ))}
              </div>
              <Card className="mt-6" title={`Score distribution — ${METRIC_LABEL[metric] ?? metric}`}>
                <div className="h-64" role="img" aria-label="Histogram comparing baseline and candidate score distributions">
                  <ResponsiveContainer>
                    <BarChart data={hist} margin={{ left: -10, right: 8, top: 8 }}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="range" tick={{ fontSize: 11, fill: "var(--muted)" }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--muted)" }} />
                      <Tooltip contentStyle={{ background: "var(--surface-solid)", border: "1px solid var(--border)", borderRadius: 14 }} cursor={{ fill: "var(--surface-2)" }} />
                      <Legend />
                      <Bar animationDuration={700} dataKey="Baseline" fill="var(--muted)" radius={[3, 3, 0, 0]} />
                      <Bar animationDuration={700} dataKey="Candidate" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-muted">Each domain has few questions, so KS tests have limited power. Treat small shifts as indicative.</p>
              </Card>
            </>
          )}
        </>
      )}
    </>
  );
}
