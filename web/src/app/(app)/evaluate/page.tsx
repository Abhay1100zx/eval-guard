"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useApi, useFetch } from "@/lib/api";
import type { Job, PromptVersion } from "@/lib/types";
import { Badge, Button, Card, ErrorBox, LiveDot, MockBanner, PageHeader, ScorerBadge, domainLabel, inputCls, pct, useDomains } from "@/components/ui";

export default function Evaluate() {
  const api = useApi();
  const { domains, byKey } = useDomains();
  const [domain, setDomain] = useState("education");
  const [runName, setRunName] = useState("");
  const [suite, setSuite] = useState("standard");
  const [promptId, setPromptId] = useState("");
  const [limit, setLimit] = useState("");
  const prompts = useFetch<{ prompts: PromptVersion[] }>("/prompts");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function poll(id: string) {
    timer.current = setTimeout(async () => {
      try {
        const j = await api<Job>(`/jobs/${id}`);
        setJob(j);
        if (j.status === "queued" || j.status === "running") poll(id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 2000);
  }

  async function start(path: string, body?: object) {
    setError(null); setJob(null);
    try {
      const { job_id } = await api<{ job_id: string }>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      setJob(await api<Job>(`/jobs/${job_id}`));
      poll(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const active = job?.status === "queued" || job?.status === "running";
  const p = job?.progress;
  const totalSteps = job ? Math.max(1, job.progress.domains_total) : 1;
  const fraction = job && p ? Math.min(1, (p.domains_done + (p.total ? p.current / p.total : 0)) / totalSteps) : 0;

  return (
    <>
      <PageHeader title="Run evaluation" subtitle="Index a domain's documents, answer every benchmark question, judge each answer, and compare with the previous comparable run." />
      <MockBanner />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Single domain">
          <div className="space-y-3">
            <div>
              <label htmlFor="d" className="mb-1 block text-xs text-muted">Domain</label>
              <select id="d" className={inputCls} value={domain} onChange={(e) => setDomain(e.target.value)}>
                {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
              </select>
              {byKey[domain] && <p className="mt-2 text-xs text-muted">{byKey[domain].description}</p>}
              {byKey[domain]?.safeguard_notice && <p className="mt-2 text-xs text-warn">⚠️ {byKey[domain].safeguard_notice}</p>}
            </div>
            <div>
              <label htmlFor="n" className="mb-1 block text-xs text-muted">Run label (optional)</label>
              <input id="n" maxLength={200} className={inputCls} value={runName} onChange={(e) => setRunName(e.target.value)} placeholder="e.g. prompt v2" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="su" className="mb-1 block text-xs text-muted">Question set</label>
                <select id="su" className={inputCls} value={suite} onChange={(e) => setSuite(e.target.value)}>
                  <option value="standard">Standard questions</option>
                  <option value="adversarial">Adversarial / safety</option>
                  <option value="all">Both</option>
                </select>
              </div>
              <div>
                <label htmlFor="ql" className="mb-1 block text-xs text-muted">Limit questions (optional)</label>
                <input id="ql" type="number" min={1} max={100} className={inputCls} value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="all" />
              </div>
            </div>
            <div>
              <label htmlFor="pr" className="mb-1 block text-xs text-muted">Prompt</label>
              <select id="pr" className={inputCls} value={promptId} onChange={(e) => setPromptId(e.target.value)}>
                <option value="">Default prompt</option>
                {(prompts.data?.prompts ?? []).filter((p) => !p.is_default).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <Button disabled={active} onClick={() => start("/evaluate/run", { domain, run_name: runName || null, suite, prompt_id: promptId || null, question_limit: limit ? Number(limit) : null })}>🚀 Start evaluation</Button>
          </div>
        </Card>
        <Card title="All domains">
          <p className="mb-3 text-sm text-muted">Runs every domain one after another. With free models this can take several minutes; a failing domain doesn&apos;t stop the batch.</p>
          <Button variant="ghost" disabled={active} onClick={() => start("/evaluate/all")}>⚡ Evaluate all {domains.length || 8} domains</Button>
        </Card>
      </div>

      {error && <div className="mt-6"><ErrorBox message={error} /></div>}

      {job && (
        <Card className="mt-6" title={`Job · ${job.kind === "all" ? "all domains" : domainLabel(byKey, job.domains[0])}`}>
          <div className="flex items-center gap-2">
            <Badge tone={job.status === "done" ? "good" : job.status === "failed" ? "bad" : "accent"}>{active && <LiveDot />}{job.status}</Badge>
            {active && p?.domain && <span className="text-sm text-muted">{domainLabel(byKey, p.domain)} · question {Math.min(p.current + 1, p.total || 1)} / {p.total || "…"}</span>}
          </div>
          {active && (
            <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round(fraction * 100)} aria-valuemin={0} aria-valuemax={100}>
              <div className="progress-fill h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(4, fraction * 100)}%` }} />
            </div>
          )}
          {job.status === "failed" && job.error && <div className="mt-3"><ErrorBox message={job.error} /></div>}
          {job.results.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr><th className="py-2 pr-4 font-medium">Domain</th><th className="pr-4 font-medium">Result</th><th className="pr-4 text-right font-medium">Faith.</th><th className="pr-4 text-right font-medium">Rel.</th><th className="pr-4 text-right font-medium">Hit</th><th className="font-medium">Drift</th></tr>
                </thead>
                <tbody>
                  {job.results.map((r) => (
                    <tr key={r.domain} className="border-t border-border align-top">
                      <td className="py-2.5 pr-4">{domainLabel(byKey, r.domain)}</td>
                      {r.run ? (
                        <>
                          <td className="pr-4"><Link href={`/runs/${r.run.id}`} className="text-accent hover:underline">view run</Link> <ScorerBadge run={r.run} /></td>
                          <td className="pr-4 text-right tabular-nums">{pct(r.run.avg_faithfulness)}</td>
                          <td className="pr-4 text-right tabular-nums">{pct(r.run.avg_relevance)}</td>
                          <td className="pr-4 text-right tabular-nums">{pct(r.run.avg_retrieval_hit_rate)}</td>
                          <td className="text-xs">
                            {r.drift_report ? <Badge tone={r.drift_report.overall_status === "HEALTHY" ? "good" : "bad"}>{r.drift_report.overall_status}</Badge>
                              : r.drift_skipped_reason ? <span className="text-warn">{r.drift_skipped_reason}</span> : <span className="text-muted">first run — no baseline</span>}
                          </td>
                        </>
                      ) : (
                        <td colSpan={5} className="text-bad">Failed: {r.error}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
