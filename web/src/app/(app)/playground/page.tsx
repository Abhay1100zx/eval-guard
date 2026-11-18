"use client";

import { useEffect, useRef, useState } from "react";
import { useApi, useFetch } from "@/lib/api";
import type { Context, PromptVersion, TestQuestion } from "@/lib/types";
import { Badge, Button, ErrorBox, MockBanner, PageHeader, inputCls, pct, scoreTone, useDomains } from "@/components/ui";

interface Judged { score: number; reasoning: string; scorer?: string }
interface Scores { faithfulness: Judged; relevance: Judged; is_mock: boolean; judge_model: string; notes: string[] }
// `notes` explains why earlier models were skipped (e.g. their daily free limit was used up); empty when the first one answered
interface Reply { answer: string; contexts: Context[]; latency_ms: number; model: string; notes: string[]; prompt_name: string; is_mock: boolean }

interface Msg {
  role: "user" | "assistant";
  content: string;
  reply?: Reply;
  scores?: Scores;
  scoring?: boolean;
  scoreError?: string;
}

const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const msgOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

export default function Chat() {
  const api = useApi();
  const { domains, byKey } = useDomains();
  const [domain, setDomain] = useState("education");
  const [promptId, setPromptId] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveFor, setSaveFor] = useState<number | null>(null);
  const gen = useRef(0); // bumped when the chat is cleared, so a reply that arrives late is dropped
  const box = useRef<HTMLDivElement>(null);

  const dom = byKey[domain];
  const { data: prompts } = useFetch<{ prompts: PromptVersion[] }>("/prompts");
  const { data: std } = useFetch<{ questions: TestQuestion[] }>(`/questions?domain=${domain}&kind=standard`);
  const starters = (std?.questions ?? []).filter((q) => q.source === "builtin").slice(0, 3).map((q) => q.question);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  function reset(next?: { domain?: string; promptId?: string }) {
    gen.current++;
    setMessages([]); setError(null); setSaveFor(null); setBusy(false); setDraft("");
    if (next?.domain !== undefined) setDomain(next.domain);
    if (next?.promptId !== undefined) setPromptId(next.promptId);
  }

  async function ask(history: Msg[]) {
    const g = gen.current;
    setBusy(true); setError(null);
    try {
      const r = await api<Reply>("/chat", {
        method: "POST",
        body: JSON.stringify({
          domain,
          prompt_id: promptId || undefined,
          messages: history.slice(-40).map((m) => ({ role: m.role, content: m.content.slice(0, 2000) })),
        }),
      });
      if (g === gen.current) setMessages([...history, { role: "assistant", content: r.answer, reply: r }]);
    } catch (e) {
      if (g === gen.current) setError(msgOf(e));
    } finally {
      if (g === gen.current) setBusy(false);
    }
  }

  function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history: Msg[] = [...messages, { role: "user", content: q }];
    setMessages(history); setDraft("");
    void ask(history);
  }

  function patch(i: number, p: Partial<Msg>, g = gen.current) {
    if (g === gen.current) setMessages((all) => all.map((m, j) => (j === i ? { ...m, ...p } : m)));
  }

  async function score(i: number) {
    const g = gen.current;
    const a = messages[i];
    patch(i, { scoring: true, scoreError: undefined });
    try {
      const s = await api<Scores>("/chat/score", {
        method: "POST",
        body: JSON.stringify({ domain, question: messages[i - 1].content, answer: a.content, contexts: (a.reply?.contexts ?? []).map((c) => c.text) }),
      });
      patch(i, { scores: s, scoring: false }, g);
    } catch (e) {
      patch(i, { scoring: false, scoreError: msgOf(e) }, g);
    }
  }

  return (
    <>
      <PageHeader
        title="Chat"
        subtitle="Talk to the chatbot the way your users would. Every answer shows the passages it came from, and you can score it or save it as a benchmark test case."
      />
      <MockBanner />

      <section className="glass flex flex-col p-4 sm:p-5">
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div>
            <label htmlFor="dom" className="mb-1 block text-xs text-muted">Documents (switching clears the chat)</label>
            <select id="dom" className={inputCls} value={domain} onChange={(e) => reset({ domain: e.target.value })}>
              {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pr" className="mb-1 block text-xs text-muted">System prompt</label>
            <select id="pr" className={inputCls} value={promptId} onChange={(e) => reset({ promptId: e.target.value })}>
              <option value="">Default (strict, grounded)</option>
              {(prompts?.prompts ?? []).filter((p) => !p.is_default).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <Button variant="ghost" onClick={() => reset()} disabled={!messages.length && !busy}>Clear chat</Button>
        </div>
        {dom?.safeguard_notice && <p className="mt-3 text-xs text-muted">ℹ️ {dom.safeguard_notice}</p>}

        <div
          ref={box}
          aria-live="polite"
          aria-label="Conversation"
          className="glass-inset mt-4 flex h-[30rem] max-h-[60vh] flex-col gap-4 overflow-y-auto rounded-3xl p-4 [scrollbar-color:color-mix(in_srgb,var(--accent)_40%,transparent)_transparent] [scrollbar-width:thin]"
        >
          {messages.length === 0 && !busy && (
            <div className="m-auto max-w-md text-center">
              <div className="text-3xl" aria-hidden>{dom?.icon ?? "💬"}</div>
              <p className="mt-2 text-sm text-muted">
                Ask anything about the {dom?.name ?? "selected"} documents. Follow-up questions work too — the chatbot sees the last few turns.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {starters.map((q) => (
                  <button key={q} type="button" onClick={() => send(q)} className="btn-spring glass rounded-full px-3.5 py-1.5 text-left text-xs hover:bg-surface">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-lg border border-accent/40 bg-accent/20 px-4 py-2.5 text-sm text-foreground">{m.content}</div>
            ) : (
              <div key={i} className="space-y-3">
                <Answer
                  m={m}
                  question={messages[i - 1]?.content ?? ""}
                  domain={domain}
                  threshold={dom?.faithfulness_threshold}
                  saving={saveFor === i}
                  onScore={() => void score(i)}
                  onSave={() => setSaveFor(saveFor === i ? null : i)}
                />
                {saveFor === i && <SaveCase domain={domain} question={messages[i - 1]?.content ?? ""} answer={m.content} onClose={() => setSaveFor(null)} />}
              </div>
            ),
          )}

          {busy && (
            <div role="status" aria-label="The chatbot is typing" className="glass w-fit rounded-3xl rounded-bl-lg px-4 py-3">
              <span className="flex gap-1.5">
                {[0, 1, 2].map((n) => <span key={n} className="live-dot inline-block size-2 rounded-full bg-muted" style={{ animationDelay: `${n * 0.18}s` }} />)}
              </span>
            </div>
          )}
        </div>

        {error && <div className="mt-4"><ErrorBox message={error} onRetry={messages.at(-1)?.role === "user" ? () => void ask(messages) : undefined} /></div>}

        <form onSubmit={(e) => { e.preventDefault(); send(draft); }} className="mt-4 flex items-end gap-3">
          <label htmlFor="msg" className="sr-only">Your message</label>
          <textarea
            id="msg"
            rows={2}
            maxLength={2000}
            className={`${inputCls} resize-none`}
            placeholder="Ask a question… (Enter to send, Shift+Enter for a new line)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(draft); }
            }}
          />
          <Button type="submit" disabled={busy || !draft.trim()}>Send</Button>
        </form>
        <p className="mt-2 text-xs text-muted">
          Each message uses one call to the answer model. Scoring an answer uses two more, so score only the answers you care about.
        </p>
      </section>
    </>
  );
}

function Answer({ m, question, domain, threshold, saving, onScore, onSave }: {
  m: Msg; question: string; domain: string; threshold?: number; saving: boolean; onScore: () => void; onSave: () => void;
}) {
  const r = m.reply;
  const s = m.scores;
  return (
    <div className="max-w-[92%] space-y-2">
      <div className="glass whitespace-pre-wrap rounded-3xl rounded-bl-lg px-4 py-2.5 text-sm">{m.content}</div>
      {r && (
        <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-muted">
          <span>{(r.latency_ms / 1000).toFixed(1)} s</span>
          <span aria-hidden>·</span>
          <span>{r.model}</span>
          {r.is_mock && <Badge tone="bad">mock LLM</Badge>}
          {r.notes.length > 0 && <Badge tone="warn" title="The first model was unavailable, so a backup answered">backup model</Badge>}
        </div>
      )}
      {r && r.notes.length > 0 && <p className="px-1 text-xs text-muted">Switched models: {r.notes.join("; ")}</p>}
      {r && r.contexts.length > 0 && (
        <details className="glass-inset rounded-2xl px-3.5 py-2 text-xs">
          <summary className="cursor-pointer font-medium">Sources used ({r.contexts.length})</summary>
          <div className="mt-2 space-y-2">
            {r.contexts.map((c, i) => (
              <blockquote key={i} className="border-l-2 border-accent/40 pl-3">
                <div className="mb-0.5 text-muted">{c.metadata?.source ?? "unknown"} · similarity {c.score.toFixed(2)}</div>
                <p className="whitespace-pre-wrap">{c.text}</p>
              </blockquote>
            ))}
          </div>
        </details>
      )}
      {s && (
        <div className="glass-inset space-y-1.5 rounded-2xl px-3.5 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={scoreTone(s.faithfulness.score, threshold)}>Faithfulness {pct(s.faithfulness.score, 0)}</Badge>
            <Badge tone={scoreTone(s.relevance.score, threshold)}>Relevance {pct(s.relevance.score, 0)}</Badge>
            {s.is_mock && <Badge tone="bad">mock judge — not a real score</Badge>}
            {!s.is_mock && (s.faithfulness.scorer === "heuristic" || s.relevance.scorer === "heuristic")
              ? <Badge tone="warn" title="No AI judge was reachable, so these numbers come from a simple word-overlap check">rough estimate, not AI-judged</Badge>
              : !s.is_mock && <Badge title="The model that marked this answer">judged by {s.judge_model}</Badge>}
          </div>
          {s.notes.length > 0 && <p className="text-muted">Switched judges: {s.notes.join("; ")}</p>}
          <p><span className="font-medium">Grounded in the sources?</span> <span className="text-muted">{s.faithfulness.reasoning}</span></p>
          <p><span className="font-medium">Answers the question?</span> <span className="text-muted">{s.relevance.reasoning}</span></p>
        </div>
      )}
      {m.scoreError && <p role="alert" className="px-1 text-xs text-bad">{m.scoreError}</p>}
      <div className="flex flex-wrap gap-2">
        {!s && (
          <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={onScore} disabled={m.scoring || !question}>
            {m.scoring ? "Scoring…" : "Score this answer"}
          </Button>
        )}
        <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={onSave} aria-expanded={saving} aria-label={`Save as test case for ${domain}`}>
          {saving ? "Hide form" : "Save as test case"}
        </Button>
      </div>
    </div>
  );
}

/** Turns a chat exchange into a permanent benchmark question (POST /questions). */
function SaveCase({ domain, question, answer, onClose }: { domain: string; question: string; answer: string; onClose: () => void }) {
  const api = useApi();
  const [kind, setKind] = useState<"standard" | "out_of_scope">("standard");
  const [q, setQ] = useState(question);
  const [truth, setTruth] = useState(answer);
  const [kw, setKw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[] | null>(null);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => { ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, []);

  function pick(k: "standard" | "out_of_scope") {
    setKind(k);
    setTruth(k === "out_of_scope" ? "The documents do not specify this." : answer);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const res = await api<{ warnings: string[] }>("/questions", {
        method: "POST",
        body: JSON.stringify({ domain, kind, question: q, ground_truth: truth, expected_keywords: kind === "standard" ? split(kw) : [], must_not_contain: [] }),
      });
      setNotes(res.warnings.length ? res.warnings : ["Saved. It will be included in the next benchmark run for this domain."]);
    } catch (err) {
      setError(msgOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section ref={ref} className="glass rise rounded-3xl p-4" aria-label="Save as test case">
      <h2 className="mb-1 text-sm font-semibold">Save as a benchmark test case</h2>
      <p className="mb-4 text-xs text-muted">Test questions are asked on their own, without the chat history, so write the question so it makes sense by itself.</p>
      {notes ? (
        <div className="space-y-3">
          <ul className="list-disc space-y-1 pl-5 text-sm">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
          <Button variant="ghost" onClick={onClose}>Done</Button>
        </div>
      ) : (
        <form onSubmit={save} className="space-y-3">
          <div>
            <label htmlFor="sk" className="mb-1 block text-xs text-muted">Type</label>
            <select id="sk" className={inputCls} value={kind} onChange={(e) => pick(e.target.value as "standard" | "out_of_scope")}>
              <option value="standard">Standard — the documents contain the answer</option>
              <option value="out_of_scope">Out of scope — the chatbot should say it doesn&apos;t know</option>
            </select>
          </div>
          <div>
            <label htmlFor="sq" className="mb-1 block text-xs text-muted">Question</label>
            <textarea id="sq" rows={2} required minLength={5} maxLength={1000} className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div>
            <label htmlFor="st" className="mb-1 block text-xs text-muted">Expected answer (check it against the documents; don&apos;t just trust the chatbot)</label>
            <textarea id="st" rows={3} required maxLength={2000} className={inputCls} value={truth} onChange={(e) => setTruth(e.target.value)} />
          </div>
          {kind === "standard" && (
            <div>
              <label htmlFor="sw" className="mb-1 block text-xs text-muted">Expected keywords (comma separated, copied exactly from the documents)</label>
              <input id="sw" className={inputCls} placeholder="e.g. 18 days, accrual" value={kw} onChange={(e) => setKw(e.target.value)} />
            </div>
          )}
          {error && <ErrorBox message={error} />}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save test case"}</Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      )}
    </section>
  );
}
