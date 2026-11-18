"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFetch } from "@/lib/api";
import type { Run } from "@/lib/types";
import {
  Card, Empty, ErrorBox, MockBanner, PageHeader, ScorerBadge, Spinner, Stat, domainLabel, fmtDate, inputCls, pct, scoreTone, useDomains,
} from "@/components/ui";

export default function Overview() {
  const { byKey, domains } = useDomains();
  const comparison = useFetch<{ comparison: Run[] }>("/comparison/domains");
  const runsRes = useFetch<{ runs: Run[] }>("/runs?limit=200");
  const [picked, setPicked] = useState("");
  const domain = picked || domains[0]?.key || "";

  // Only runs judged by a real LLM/heuristic count as measurements; mock and pre-tracking runs are not data.
  const isReal = (r: Run) => !!r.scorer && !r.scorer.includes("mock") && !r.is_simulated;
  const runs = useMemo(() => (runsRes.data?.runs ?? []).filter((r) => !r.is_simulated), [runsRes.data]);
  const realRuns = useMemo(() => runs.filter(isReal), [runs]);
  const allLatest = comparison.data?.comparison ?? [];
  const latest = allLatest.filter(isReal);
  const unscored = allLatest.length - latest.length;
  const avg = (f: (r: Run) => number) => (latest.length ? latest.reduce((s, r) => s + f(r), 0) / latest.length : 0);

  const trend = useMemo(
    () =>
      realRuns
        .filter((r) => r.domain === domain)
        .slice()
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
        .map((r) => ({
          t: new Date(r.timestamp + "Z").toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
          Faithfulness: r.avg_faithfulness,
          Relevance: r.avg_relevance,
          "Hit rate": r.avg_retrieval_hit_rate ?? 0,
        })),
    [realRuns, domain],
  );

  if (runsRes.loading || comparison.loading) return <Spinner />;
  if (runsRes.error) return <ErrorBox message={runsRes.error} onRetry={runsRes.reload} />;

  return (
    <>
      <PageHeader title="Overview" subtitle="Latest quality across every domain, and how it has moved over time." />
      <MockBanner />
      {realRuns.length === 0 && runs.length === 0 ? (
        <Empty title="No evaluation runs yet" hint="Run your first benchmark to see quality, retrieval and latency here." href="/evaluate" cta="Run an evaluation" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat delay={0} label="Domains with real scores" value={`${latest.length} / ${domains.length || 8}`} tone={latest.length ? undefined : "bad"} />
            <Stat delay={1} label="Avg faithfulness" value={pct(avg((r) => r.avg_faithfulness))} tone={scoreTone(avg((r) => r.avg_faithfulness))} hint="Grounded in retrieved context" />
            <Stat delay={2} label="Avg relevance" value={pct(avg((r) => r.avg_relevance))} tone={scoreTone(avg((r) => r.avg_relevance))} hint="Matches ground truth" />
            <Stat delay={3} label="Avg retrieval hit rate" value={pct(avg((r) => r.avg_retrieval_hit_rate ?? 0))} tone={scoreTone(avg((r) => r.avg_retrieval_hit_rate ?? 0))} />
            <Stat delay={4} label="Avg latency" value={`${avg((r) => r.avg_latency_ms).toFixed(0)} ms`} />
          </div>

          {unscored > 0 && (
            <div role="status" className="glass rise mt-4 p-3.5 text-sm" style={{ background: "color-mix(in srgb, var(--warn) 12%, var(--glass))" }}>
              <strong className="text-warn">{unscored} of {allLatest.length} domains have no real score yet.</strong>{" "}
              Their latest run used the mock judge (or predates scorer tracking), so they are left out of the averages above.{" "}
              <Link href="/evaluate" className="font-medium text-accent underline">Run an evaluation</Link>
            </div>
          )}

          <Card delay={5} className="mt-6" title="Quality over time">
            <div className="mb-3 max-w-xs">
              <label htmlFor="dom" className="mb-1 block text-xs text-muted">Domain</label>
              <select id="dom" className={inputCls} value={domain} onChange={(e) => setPicked(e.target.value)}>
                {domains.map((d) => (
                  <option key={d.key} value={d.key}>{d.icon} {d.name}</option>
                ))}
              </select>
            </div>
            {trend.length < 2 ? (
              <p className="py-10 text-center text-sm text-muted">A trend needs at least two real-scored runs in this domain.</p>
            ) : (
              <div className="h-72" role="img" aria-label="Line chart of faithfulness, relevance and hit rate across runs">
                <ResponsiveContainer>
                  <LineChart data={trend} margin={{ left: -10, right: 8, top: 8 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                    <XAxis dataKey="t" tick={{ fontSize: 11, fill: "var(--muted)" }} />
                    <YAxis domain={[0, 1]} tickFormatter={(v) => `${v * 100}%`} tick={{ fontSize: 11, fill: "var(--muted)" }} />
                    <Tooltip formatter={(v) => pct(Number(v))} contentStyle={{ background: "var(--surface-solid)", border: "1px solid var(--border)", borderRadius: 14 }} />
                    <Legend />
                    <Line animationDuration={800} animationEasing="ease-out" type="monotone" dataKey="Faithfulness" stroke="var(--good)" strokeWidth={2} dot />
                    <Line animationDuration={800} animationEasing="ease-out" type="monotone" dataKey="Relevance" stroke="var(--accent)" strokeWidth={2} dot />
                    <Line animationDuration={800} animationEasing="ease-out" type="monotone" dataKey="Hit rate" stroke="var(--warn)" strokeWidth={2} strokeDasharray="4 3" dot />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>

          <Card delay={6} className="mt-6" title="Recent runs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Run</th>
                    <th className="pr-4 font-medium">Domain</th>
                    <th className="pr-4 font-medium">Scorer</th>
                    <th className="pr-4 text-right font-medium">Faith.</th>
                    <th className="pr-4 text-right font-medium">Rel.</th>
                    <th className="pr-4 text-right font-medium">Hit</th>
                    <th className="text-right font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.slice(0, 8).map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-2.5 pr-4">
                        <Link href={`/runs/${r.id}`} className="font-medium text-accent hover:underline">{r.run_name}</Link>
                      </td>
                      <td className="pr-4">{domainLabel(byKey, r.domain)}</td>
                      <td className="pr-4"><ScorerBadge run={r} /></td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_faithfulness)}</td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_relevance)}</td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_retrieval_hit_rate)}</td>
                      <td className="text-right text-muted">{fmtDate(r.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </>
  );
}
