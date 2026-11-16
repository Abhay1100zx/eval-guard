"use client";

import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFetch } from "@/lib/api";
import type { Run } from "@/lib/types";
import { Card, Empty, ErrorBox, MockBanner, PageHeader, ScorerBadge, Spinner, pct, useDomains } from "@/components/ui";

function MetricChart({ title, data, dataKey, pctAxis = true, target }: {
  title: string; data: Record<string, string | number>[]; dataKey: string; pctAxis?: boolean; target?: number;
}) {
  return (
    <Card title={title}>
      <div className="h-64" role="img" aria-label={`${title} by domain`}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ left: -10, right: 8, top: 8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={0} angle={-25} textAnchor="end" height={60} />
            <YAxis domain={pctAxis ? [0, 1] : undefined} tickFormatter={(v) => (pctAxis ? `${v * 100}%` : `${v}`)} tick={{ fontSize: 11, fill: "var(--muted)" }} />
            <Tooltip formatter={(v) => (pctAxis ? pct(Number(v)) : `${Number(v).toFixed(0)} ms`)} contentStyle={{ background: "var(--surface-solid)", border: "1px solid var(--border)", borderRadius: 14 }} cursor={{ fill: "var(--surface-2)" }} />
            {target !== undefined && <ReferenceLine y={target} stroke="var(--warn)" strokeDasharray="4 3" label={{ value: `target ${target * 100}%`, fontSize: 10, fill: "var(--warn)", position: "insideTopRight" }} />}
            <Bar animationDuration={800} animationEasing="ease-out" dataKey={dataKey} radius={[4, 4, 0, 0]}>
              {data.map((d) => (
                <Cell key={String(d.name)} fill={!pctAxis ? "var(--accent)" : Number(d[dataKey]) >= (target ?? 0) ? "var(--good)" : "var(--bad)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export default function Benchmark() {
  const { byKey } = useDomains();
  const { data, loading, error, reload } = useFetch<{ comparison: Run[] }>("/comparison/domains");

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const rows = data?.comparison ?? [];
  const chart = rows.map((r) => ({
    name: byKey[r.domain]?.name ?? r.domain,
    faith: r.avg_faithfulness, rel: r.avg_relevance, hit: r.avg_retrieval_hit_rate ?? 0, lat: r.avg_latency_ms,
  }));

  return (
    <>
      <PageHeader title="Cross-domain benchmark" subtitle="Latest real run per domain (simulated runs are excluded). Green bars meet the 75% target." />
      <MockBanner />
      <div className="glass rise mb-6 p-3.5 text-sm text-muted">
        🛡️ Healthcare, banking and legal use synthetic reference documents. High scores reflect grounding and retrieval fidelity, not clinical,
        regulatory or legal certification.
      </div>
      {rows.length === 0 ? (
        <Empty title="Nothing to compare yet" hint="Run evaluations in at least one domain." href="/evaluate" cta="Run an evaluation" />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <MetricChart title="Faithfulness" data={chart} dataKey="faith" target={0.75} />
            <MetricChart title="Answer relevance" data={chart} dataKey="rel" target={0.75} />
            <MetricChart title="Retrieval hit rate" data={chart} dataKey="hit" target={0.75} />
            <MetricChart title="Average latency (ms)" data={chart} dataKey="lat" pctAxis={false} />
          </div>
          <Card className="mt-6" title="Summary matrix">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Domain</th><th className="pr-4 font-medium">Scorer</th>
                    <th className="pr-4 text-right font-medium">Faith.</th><th className="pr-4 text-right font-medium">Rel.</th>
                    <th className="pr-4 text-right font-medium">Hit</th><th className="pr-4 text-right font-medium">MRR</th>
                    <th className="pr-4 text-right font-medium">Latency</th><th className="text-right font-medium">Qs</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-2.5 pr-4 font-medium">{byKey[r.domain]?.icon} {byKey[r.domain]?.name ?? r.domain}</td>
                      <td className="pr-4"><ScorerBadge run={r} /></td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_faithfulness)}</td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_relevance)}</td>
                      <td className="pr-4 text-right tabular-nums">{pct(r.avg_retrieval_hit_rate)}</td>
                      <td className="pr-4 text-right tabular-nums">{r.avg_mrr?.toFixed(2) ?? "—"}</td>
                      <td className="pr-4 text-right tabular-nums">{r.avg_latency_ms.toFixed(0)} ms</td>
                      <td className="text-right tabular-nums">{r.total_questions}</td>
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
