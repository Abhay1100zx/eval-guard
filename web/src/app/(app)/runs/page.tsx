"use client";

import Link from "next/link";
import { useState } from "react";
import { useFetch } from "@/lib/api";
import type { Run } from "@/lib/types";
import { Card, Empty, ErrorBox, PageHeader, ScorerBadge, Spinner, domainLabel, fmtDate, inputCls, pct, useDomains } from "@/components/ui";

export default function Runs() {
  const { byKey, domains } = useDomains();
  const [domain, setDomain] = useState("");
  const [showSim, setShowSim] = useState(false);
  const { data: raw, loading, error, reload } = useFetch<{ runs: Run[] }>(`/runs?limit=200${domain ? `&domain=${domain}` : ""}`);

  const data = raw ? { runs: raw.runs.filter((r) => showSim || !r.is_simulated) } : null;
  const hidden = raw ? raw.runs.length - (data?.runs.length ?? 0) : 0;

  return (
    <>
      <PageHeader
        title="Runs"
        subtitle="Every evaluation run. Open one to inspect each question, the retrieved context and the judge's reasoning."
        actions={
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex items-center gap-2 pb-2.5 text-sm text-muted">
              <input type="checkbox" checked={showSim} onChange={(e) => setShowSim(e.target.checked)} className="size-4 accent-[var(--accent)]" />
              Show simulated{hidden > 0 ? ` (${hidden} hidden)` : ""}
            </label>
            <div>
            <label htmlFor="d" className="mb-1 block text-xs text-muted">Domain</label>
            <select id="d" className={inputCls} value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">All domains</option>
              {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
            </select>
            </div>
          </div>
        }
      />
      {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.runs.length ? (
        <Empty title="No runs" hint="Nothing has been evaluated for this selection yet." href="/evaluate" cta="Run an evaluation" />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2 pr-4 font-medium">Run</th><th className="pr-4 font-medium">Domain</th>
                  <th className="pr-4 font-medium">Scorer</th><th className="pr-4 font-medium">Model</th>
                  <th className="pr-4 text-right font-medium">Faith.</th><th className="pr-4 text-right font-medium">Rel.</th>
                  <th className="pr-4 text-right font-medium">Hit</th><th className="text-right font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="py-2.5 pr-4"><Link href={`/runs/${r.id}`} className="font-medium text-accent hover:underline">{r.run_name}</Link></td>
                    <td className="pr-4 whitespace-nowrap">{domainLabel(byKey, r.domain)}</td>
                    <td className="pr-4"><ScorerBadge run={r} /></td>
                    <td className="max-w-40 truncate pr-4 text-muted" title={r.model_name ?? ""}>{r.model_name}</td>
                    <td className="pr-4 text-right tabular-nums">{pct(r.avg_faithfulness)}</td>
                    <td className="pr-4 text-right tabular-nums">{pct(r.avg_relevance)}</td>
                    <td className="pr-4 text-right tabular-nums">{pct(r.avg_retrieval_hit_rate)}</td>
                    <td className="whitespace-nowrap text-right text-muted">{fmtDate(r.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
