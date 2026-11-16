"use client";

import Link from "next/link";
import { useFetch } from "@/lib/api";
import type { Experiment } from "@/lib/types";
import { Badge, Card, Empty, ErrorBox, LiveDot, PageHeader, Spinner, domainLabel, fmtDate, statusTone, useDomains } from "@/components/ui";

export default function Experiments() {
  const { byKey } = useDomains();
  const { data, loading, error, reload } = useFetch<{ experiments: Experiment[] }>("/experiments");

  return (
    <>
      <PageHeader
        title="Experiments"
        subtitle="Run the same questions through different prompts or different models and compare the results side by side."
        actions={
          <div className="flex gap-2">
            <Link href="/experiments/new?kind=prompt" className="glass-inset btn-spring inline-flex items-center rounded-full px-5 py-2 text-sm font-medium">Compare prompts</Link>
            <Link href="/experiments/new?kind=model" className="btn-primary btn-spring inline-flex items-center rounded-full px-5 py-2 text-sm font-medium text-white">Compare models</Link>
          </div>
        }
      />
      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.experiments.length ? (
        <Empty title="No experiments yet" hint="Try two prompt wordings on one domain, or two models on the same prompt. 8 questions per variant is a good first pass." href="/experiments/new?kind=prompt" cta="Compare prompts" />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2 pr-4 font-medium">Experiment</th><th className="pr-4 font-medium">Compares</th>
                  <th className="pr-4 font-medium">Domain</th><th className="pr-4 font-medium">Suite</th>
                  <th className="pr-4 font-medium">Status</th><th className="text-right font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {data.experiments.map((e) => (
                  <tr key={e.id} className="border-t border-border align-top">
                    <td className="py-2.5 pr-4"><Link href={`/experiments/${e.id}`} className="font-medium text-accent hover:underline">{e.name}</Link></td>
                    <td className="pr-4"><Badge>{e.kind === "prompt" ? "prompts" : "models"}</Badge> <span className="text-muted">{e.variants.map((v) => v.label).join(" vs ")}</span></td>
                    <td className="whitespace-nowrap pr-4">{domainLabel(byKey, e.domain)}</td>
                    <td className="pr-4">{e.suite}{e.question_limit ? ` · ${e.question_limit} q` : ""}</td>
                    <td className="pr-4"><Badge tone={statusTone(e.status)}>{e.status === "running" && <LiveDot />}{e.status}</Badge></td>
                    <td className="whitespace-nowrap text-right text-muted">{fmtDate(e.created_at)}</td>
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
