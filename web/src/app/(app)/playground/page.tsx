"use client";

import { useState } from "react";
import { useApi } from "@/lib/api";
import type { Context } from "@/lib/types";
import { Badge, Button, Card, ErrorBox, MockBanner, PageHeader, Spinner, inputCls, pct, scoreTone, useDomains } from "@/components/ui";

interface Answer {
  answer: string;
  retrieved_contexts: Context[];
  faithfulness: { score: number; reasoning: string; scorer: string };
  relevance: { score: number; reasoning: string };
  latency_ms: number;
  is_mock: boolean;
  safeguard_notice: string | null;
}

export default function Playground() {
  const api = useApi();
  const { domains, byKey } = useDomains();
  const [domain, setDomain] = useState("education");
  const [typed, setTyped] = useState<string | null>(null); // null = show the domain sample question
  const [topK, setTopK] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [out, setOut] = useState<Answer | null>(null);

  const dom = byKey[domain];
  const question = typed ?? dom?.sample_question ?? "";

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setOut(null);
    try {
      setOut(await api<Answer>("/rag/query", { method: "POST", body: JSON.stringify({ question, domain, top_k: topK }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Playground" subtitle="Ask any question against a domain's knowledge base and see the answer scored in real time." />
      <MockBanner />
      <Card>
        <form onSubmit={ask} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <div>
              <label htmlFor="dom" className="mb-1 block text-xs text-muted">Domain</label>
              <select id="dom" className={inputCls} value={domain} onChange={(e) => { setDomain(e.target.value); setTyped(null); }}>
                {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="k" className="mb-1 block text-xs text-muted">Chunks (top-k)</label>
              <input id="k" type="number" min={1} max={20} className={inputCls} value={topK} onChange={(e) => setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
            </div>
          </div>
          <div>
            <label htmlFor="q" className="mb-1 block text-xs text-muted">Question</label>
            <textarea id="q" rows={2} minLength={3} maxLength={2000} required className={inputCls} value={question} onChange={(e) => setTyped(e.target.value)} />
          </div>
          {dom?.safeguard_notice && <p className="text-xs text-muted">ℹ️ {dom.safeguard_notice}</p>}
          <Button type="submit" disabled={busy || !question.trim()}>{busy ? "Retrieving & scoring…" : "Run RAG & evaluate"}</Button>
        </form>
      </Card>

      {busy && <Spinner label="Retrieving context, generating an answer and judging it (free models can take a minute)…" />}
      {error && <div className="mt-6"><ErrorBox message={error} /></div>}
      {out && (
        <div className="mt-6 space-y-4">
          {out.is_mock && <Badge tone="bad">mock LLM — scores are not real</Badge>}
          <Card title="Answer"><p className="whitespace-pre-wrap">{out.answer}</p></Card>
          <div className="grid gap-4 md:grid-cols-3">
            <Card title="Faithfulness">
              <div className="text-3xl font-semibold tabular-nums">{pct(out.faithfulness.score)}</div>
              <Badge tone={scoreTone(out.faithfulness.score, dom?.faithfulness_threshold)}>{out.faithfulness.scorer}</Badge>
              <p className="mt-2 text-sm text-muted">{out.faithfulness.reasoning}</p>
            </Card>
            <Card title="Relevance">
              <div className="text-3xl font-semibold tabular-nums">{pct(out.relevance.score)}</div>
              <p className="mt-2 text-sm text-muted">{out.relevance.reasoning}</p>
            </Card>
            <Card title="Latency"><div className="text-3xl font-semibold tabular-nums">{out.latency_ms.toFixed(0)} ms</div></Card>
          </div>
          <Card title="Retrieved context">
            <div className="space-y-2">
              {out.retrieved_contexts.map((c, i) => (
                <blockquote key={i} className="glass-inset rounded-2xl p-3.5 text-sm">
                  <div className="mb-1 text-xs text-muted">Chunk {i + 1} · {c.metadata?.source ?? "unknown"} · similarity {c.score.toFixed(3)}</div>
                  <p className="whitespace-pre-wrap">{c.text}</p>
                </blockquote>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
