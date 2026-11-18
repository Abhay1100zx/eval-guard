"use client";

import { useEffect, useRef, useState } from "react";
import { useApi, useApiStream, useFetch } from "@/lib/api";
import type { ChatSummary, Context, PromptVersion, TestQuestion } from "@/lib/types";
import { Markdown } from "@/components/markdown";
import { Badge, Button, ErrorBox, MockBanner, PageHeader, inputCls, pct, scoreTone, useDomains } from "@/components/ui";

interface Judged { score: number; reasoning: string; scorer?: string }
interface Scores { faithfulness: Judged; relevance: Judged; is_mock: boolean; judge_model: string; notes: string[] }
// What the API tells us about an answer. While it is still being written only `contexts` and `retrieval_query` are known.
// `notes` explains why earlier models were skipped (e.g. their daily free limit was used up); empty when the first one answered.
interface Reply {
  contexts: Context[];
  notes: string[];
  retrieval_query?: string;
  latency_ms?: number;
  model?: string;
  prompt_name?: string;
  is_mock?: boolean;
}
type StreamEvent =
  | { type: "meta"; contexts: Context[]; retrieval_query: string }
  | { type: "token"; text: string }
  | { type: "done"; answer: string; model: string; notes: string[]; latency_ms: number; prompt_name: string; is_mock: boolean }
  | { type: "error"; status: number; message: string };

interface Msg {
  role: "user" | "assistant";
  content: string;
  reply?: Reply;
  scores?: Scores;
  scoring?: boolean;
  scoreError?: string;
  feedback?: "up" | "down";
  streaming?: boolean;
  partial?: "stopped" | "error"; // the answer was cut off, by the user or by a failure
}
interface SavedChat { id: string; title: string; domain: string; prompt_id: string | null; messages: Msg[] }
type SaveMode = "plain" | "up" | "down";

const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const msgOf = (e: unknown) => (e instanceof Error ? e.message : String(e));
const newId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`);
/** The answer without its [1] citations or markdown emphasis: what to judge, and what to prefill as an expected answer. */
const plain = (s: string) => s.replace(/\s*\[\d{1,2}\]/g, "").replace(/\*\*|__/g, "").trim();
const titleOf = (messages: Msg[]) => (messages.find((m) => m.role === "user")?.content ?? "New chat").slice(0, 60);
/** What gets saved: everything the page shows, minus transient flags. This exact string is also how "unchanged" is detected. */
const bodyOf = (messages: Msg[], domain: string, promptId: string) =>
  JSON.stringify({
    title: titleOf(messages),
    domain,
    prompt_id: promptId || null,
    messages: messages.filter((m) => !m.streaming).map((m) => { const { scoring, streaming, ...keep } = m; void scoring; void streaming; return keep; }),
  });
const shortDate = (ts: string) => new Date(ts + (ts.endsWith("Z") ? "" : "Z")).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function Chat() {
  const api = useApi();
  const stream = useApiStream();
  const { domains, byKey } = useDomains();
  const [domain, setDomain] = useState("education");
  const [promptId, setPromptId] = useState("");
  const [chatId, setChatId] = useState<string | null>(null); // made on the first message
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveFor, setSaveFor] = useState<{ index: number; mode: SaveMode } | null>(null);
  const [copied, setCopied] = useState<{ i: number; result: "ok" | "failed" } | null>(null);
  const gen = useRef(0); // bumped on clear/switch, so a reply that arrives late is dropped
  const abort = useRef<AbortController | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const savedBody = useRef(""); // what the server already has for this chat

  const dom = byKey[domain];
  const { data: prompts } = useFetch<{ prompts: PromptVersion[] }>("/prompts");
  const { data: std } = useFetch<{ questions: TestQuestion[] }>(`/questions?domain=${domain}&kind=standard`);
  const history = useFetch<{ chats: ChatSummary[] }>("/chats");
  const reloadHistory = history.reload;
  const starters = (std?.questions ?? []).filter((q) => q.source === "builtin").slice(0, 3).map((q) => q.question);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // Save after every finished change (not while an answer is being written), a moment after the last one.
  useEffect(() => {
    if (busy || !chatId || messages.length === 0) return;
    const body = bodyOf(messages, domain, promptId);
    if (body === savedBody.current) return;
    const t = setTimeout(() => {
      api(`/chats/${chatId}`, { method: "PUT", body })
        .then(() => { savedBody.current = body; reloadHistory(); })
        .catch(() => {}); // saving is a convenience: a failure must not get in the way of chatting
    }, 800);
    return () => clearTimeout(t);
  }, [messages, busy, chatId, domain, promptId, api, reloadHistory]);

  /** Start a fresh conversation, optionally with another domain or prompt. */
  function reset(next?: { domain?: string; promptId?: string }) {
    abort.current?.abort();
    gen.current++;
    setMessages([]); setError(null); setSaveFor(null); setBusy(false); setDraft(""); setChatId(null);
    savedBody.current = "";
    if (next?.domain !== undefined) setDomain(next.domain);
    if (next?.promptId !== undefined) setPromptId(next.promptId);
  }

  async function openChat(id: string) {
    abort.current?.abort();
    gen.current++;
    setBusy(false); setError(null); setSaveFor(null);
    try {
      const c = await api<SavedChat>(`/chats/${id}`);
      const pid = prompts?.prompts.some((p) => p.id === c.prompt_id) ? (c.prompt_id ?? "") : ""; // the prompt may have been deleted since
      savedBody.current = bodyOf(c.messages, c.domain, pid); // so opening a chat doesn't re-save it
      setChatId(id); setDomain(c.domain); setPromptId(pid); setMessages(c.messages);
    } catch (e) {
      setError(msgOf(e));
    }
  }

  async function deleteChat(id: string) {
    if (!window.confirm("Delete this chat?")) return;
    try {
      await api(`/chats/${id}`, { method: "DELETE" });
      if (id === chatId) reset();
      reloadHistory();
    } catch (e) {
      setError(msgOf(e));
    }
  }

  /** Ask the model about `base` (which ends with a user message) and write the answer into the transcript as it arrives. */
  async function ask(base: Msg[]) {
    const g = ++gen.current;
    const ctrl = new AbortController();
    abort.current = ctrl;
    setBusy(true); setError(null);
    const at = base.length; // where the answer goes
    const update = (fn: (m: Msg) => Msg) => { if (g === gen.current) setMessages((all) => all.map((m, i) => (i === at ? fn(m) : m))); };
    setMessages([...base, { role: "assistant", content: "", streaming: true, reply: { contexts: [], notes: [] } }]);
    try {
      await stream<StreamEvent>(
        "/chat/stream",
        { domain, prompt_id: promptId || undefined, messages: base.slice(-40).map((m) => ({ role: m.role, content: m.content.slice(0, 2000) })) },
        (e) => {
          if (g !== gen.current) return;
          if (e.type === "meta") update((m) => ({ ...m, reply: { ...(m.reply ?? { notes: [] }), notes: m.reply?.notes ?? [], contexts: e.contexts, retrieval_query: e.retrieval_query } }));
          else if (e.type === "token") update((m) => ({ ...m, content: m.content + e.text }));
          else if (e.type === "done")
            update((m) => ({ ...m, content: e.answer || m.content, streaming: false,
              reply: { contexts: m.reply?.contexts ?? [], retrieval_query: m.reply?.retrieval_query, model: e.model, notes: e.notes, latency_ms: e.latency_ms, prompt_name: e.prompt_name, is_mock: e.is_mock } }));
          else {
            update((m) => ({ ...m, streaming: false, partial: m.content ? "error" : undefined }));
            setError(e.message);
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if (g !== gen.current) return;
      if (err instanceof DOMException && err.name === "AbortError") update((m) => ({ ...m, streaming: false, partial: m.content ? "stopped" : undefined }));
      else { update((m) => ({ ...m, streaming: false, partial: m.content ? "error" : undefined })); setError(msgOf(err)); }
    } finally {
      if (g === gen.current) {
        setBusy(false);
        setMessages((all) => { const last = all[all.length - 1]; return last?.role === "assistant" && !last.content ? all.slice(0, -1) : all; }); // nothing was written
      }
    }
  }

  function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    if (!chatId) setChatId(newId());
    const next: Msg[] = [...messages, { role: "user", content: q }];
    setMessages(next); setDraft("");
    void ask(next);
  }

  function regenerate() {
    const last = messages.length - 1;
    if (busy || messages[last]?.role !== "assistant") return;
    setSaveFor(null);
    void ask(messages.slice(0, last));
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
        body: JSON.stringify({ domain, question: messages[i - 1].content, answer: plain(a.content), contexts: (a.reply?.contexts ?? []).map((c) => c.text) }),
      });
      patch(i, { scores: s, scoring: false }, g);
    } catch (e) {
      patch(i, { scoring: false, scoreError: msgOf(e) }, g);
    }
  }

  function copy(i: number) {
    const flash = (result: "ok" | "failed") => {
      setCopied({ i, result });
      setTimeout(() => setCopied((c) => (c?.i === i ? null : c)), 1500);
    };
    // the browser refuses when the page isn't focused or isn't on https/localhost: say so instead of doing nothing
    (navigator.clipboard?.writeText(messages[i].content) ?? Promise.reject(new Error("no clipboard"))).then(() => flash("ok"), () => flash("failed"));
  }

  /** A thumb marks the answer and opens the test-case form: 👍 offers the answer as the expected one, 👎 asks for the right one. */
  function rate(i: number, v: "up" | "down") {
    if (messages[i].feedback === v) { patch(i, { feedback: undefined }); setSaveFor(null); return; }
    patch(i, { feedback: v });
    setSaveFor({ index: i, mode: v });
  }

  const chats = history.data?.chats ?? [];
  const last = messages.length - 1;

  return (
    <>
      <PageHeader
        title="Chat"
        subtitle="Talk to the chatbot the way your users would. Every answer shows the passages it came from, and you can score it, rate it, or save it as a benchmark test case."
      />
      <MockBanner />

      <div className="grid gap-4 lg:grid-cols-[15rem_1fr]">
        <aside className="glass p-3 lg:sticky lg:top-6 lg:self-start" aria-label="Chat history">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">History</h2>
            <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => reset()} disabled={!messages.length && !busy}>＋ New chat</Button>
          </div>
          {chats.length === 0 ? (
            <p className="text-xs text-muted">{history.loading ? "Loading…" : "Your chats are saved here automatically, only you can see them."}</p>
          ) : (
            <ul className="max-h-40 space-y-1 overflow-y-auto lg:max-h-[28rem]">
              {chats.map((c) => (
                <li key={c.id} className={`group flex items-center gap-1 rounded-xl ${c.id === chatId ? "bg-accent/15" : "hover:bg-surface-2"}`}>
                  <button type="button" onClick={() => void openChat(c.id)} className="min-w-0 flex-1 px-2.5 py-1.5 text-left" aria-current={c.id === chatId || undefined}>
                    <div className="truncate text-xs font-medium">{byKey[c.domain]?.icon ?? "💬"} {c.title}</div>
                    <div className="text-[0.7rem] text-muted">{shortDate(c.updated_at)}</div>
                  </button>
                  <button type="button" onClick={() => void deleteChat(c.id)} aria-label={`Delete chat: ${c.title}`} className="mr-1 rounded-full px-2 py-1 text-xs text-muted opacity-60 hover:bg-bad/15 hover:text-bad hover:opacity-100 focus:opacity-100">✕</button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="glass flex min-w-0 flex-col p-4 sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="dom" className="mb-1 block text-xs text-muted">Documents (switching starts a new chat)</label>
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
          </div>
          {dom?.safeguard_notice && <p className="mt-3 text-xs text-muted">ℹ️ {dom.safeguard_notice}</p>}

          <div
            ref={box}
            aria-live="polite"
            aria-busy={busy}
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
              m.role === "assistant" && m.streaming && !m.content ? null : m.role === "user" ? ( // nothing written yet: the dots below stand in
                <div key={i} className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-lg border border-accent/40 bg-accent/20 px-4 py-2.5 text-sm text-foreground">{m.content}</div>
              ) : (
                <div key={i} className="space-y-3">
                  <Answer
                    m={m}
                    question={messages[i - 1]?.content ?? ""}
                    threshold={dom?.faithfulness_threshold}
                    isLast={i === last}
                    busy={busy}
                    saving={saveFor?.index === i}
                    copied={copied?.i === i ? copied.result : undefined}
                    onScore={() => void score(i)}
                    onSave={() => setSaveFor(saveFor?.index === i ? null : { index: i, mode: "plain" })}
                    onCopy={() => copy(i)}
                    onRegenerate={regenerate}
                    onRate={(v) => rate(i, v)}
                  />
                  {saveFor?.index === i && (
                    <SaveCase
                      key={`${i}-${saveFor.mode}`}
                      domain={domain}
                      mode={saveFor.mode}
                      question={messages[i - 1]?.content ?? ""}
                      answer={saveFor.mode === "down" ? "" : plain(m.content)}
                      onClose={() => setSaveFor(null)}
                    />
                  )}
                </div>
              ),
            )}

            {!busy && !error && messages[last]?.role === "user" && ( // stopped before anything was written, or the page was closed mid-answer
              <div className="glass flex w-fit items-center gap-3 rounded-3xl rounded-bl-lg px-4 py-2 text-xs text-muted">
                No answer yet.
                <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => void ask(messages)}>↻ Try again</Button>
              </div>
            )}

            {busy && !messages[last]?.content ? (
              <div role="status" aria-label="The chatbot is thinking" className="glass w-fit rounded-3xl rounded-bl-lg px-4 py-3">
                <span className="flex gap-1.5">
                  {[0, 1, 2].map((n) => <span key={n} className="live-dot inline-block size-2 rounded-full bg-muted" style={{ animationDelay: `${n * 0.18}s` }} />)}
                </span>
              </div>
            ) : null}
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
            {busy ? (
              <Button type="button" variant="ghost" onClick={() => abort.current?.abort()}>■ Stop</Button>
            ) : (
              <Button type="submit" disabled={!draft.trim()}>Send</Button>
            )}
          </form>
          <p className="mt-2 text-xs text-muted">
            Each message uses one call to the answer model (a follow-up that needs its context spelled out uses one more). Scoring an answer uses two more, so score only the answers you care about.
          </p>
        </section>
      </div>
    </>
  );
}

function Answer({ m, question, threshold, isLast, busy, saving, copied, onScore, onSave, onCopy, onRegenerate, onRate }: {
  m: Msg; question: string; threshold?: number; isLast: boolean; busy: boolean; saving: boolean; copied?: "ok" | "failed";
  onScore: () => void; onSave: () => void; onCopy: () => void; onRegenerate: () => void; onRate: (v: "up" | "down") => void;
}) {
  const r = m.reply;
  const s = m.scores;
  const sources = r?.contexts ?? [];
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState<number | null>(null);
  const refs = useRef<(HTMLQuoteElement | null)[]>([]);
  const searched = r?.retrieval_query && r.retrieval_query.trim() !== question.trim() ? r.retrieval_query : null;

  function cite(n: number) {
    setOpen(true);
    setHi(n);
    requestAnimationFrame(() => refs.current[n - 1]?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }

  const small = "!px-3 !py-1 text-xs";
  return (
    <div className="max-w-[94%] space-y-2">
      <div className="glass rounded-3xl rounded-bl-lg px-4 py-2.5 text-sm">
        <Markdown text={m.content} sources={sources.length} onCite={cite} />
        {m.streaming && <span aria-hidden className="live-dot ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 rounded-sm bg-current" />}
        {m.partial && <div className="mt-1"><Badge tone="warn">{m.partial === "stopped" ? "stopped" : "cut off by an error"}</Badge></div>}
      </div>
      {r && !m.streaming && (
        <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-muted">
          {r.latency_ms !== undefined && <span>{(r.latency_ms / 1000).toFixed(1)} s</span>}
          {r.model && <><span aria-hidden>·</span><span>{r.model}</span></>}
          {r.is_mock && <Badge tone="bad">mock LLM</Badge>}
          {r.notes.length > 0 && <Badge tone="warn" title="The first model was unavailable, so a backup answered">backup model</Badge>}
        </div>
      )}
      {r && r.notes.length > 0 && !m.streaming && <p className="px-1 text-xs text-muted">Switched models: {r.notes.join("; ")}</p>}
      {searched && <p className="px-1 text-xs text-muted">Searched the documents for: <em>{searched}</em></p>}
      {sources.length > 0 && (
        <details className="glass-inset rounded-2xl px-3.5 py-2 text-xs" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
          <summary className="cursor-pointer font-medium">Sources used ({sources.length})</summary>
          <div className="mt-2 space-y-2">
            {sources.map((c, i) => (
              <blockquote
                key={i}
                ref={(el) => { refs.current[i] = el; }}
                className={`rounded-lg border-l-2 py-1 pl-3 transition ${hi === i + 1 ? "border-accent bg-accent/10" : "border-accent/40"}`}
              >
                <div className="mb-0.5 text-muted"><span className="font-semibold text-accent">[{i + 1}]</span> {c.metadata?.source ?? "unknown"} · similarity {c.score.toFixed(2)}</div>
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
      {!m.streaming && (
        <div className="flex flex-wrap gap-2">
          {!s && <Button variant="ghost" className={small} onClick={onScore} disabled={m.scoring || !question || !m.content}>{m.scoring ? "Scoring…" : "Score this answer"}</Button>}
          <Button variant="ghost" className={small} onClick={onCopy}>{copied === "ok" ? "Copied ✓" : copied === "failed" ? "Copy failed" : "Copy"}</Button>
          {isLast && <Button variant="ghost" className={small} onClick={onRegenerate} disabled={busy}>↻ Regenerate</Button>}
          <Button variant="ghost" className={`${small} ${m.feedback === "up" ? "!bg-good/20 !text-good" : ""}`} onClick={() => onRate("up")} aria-pressed={m.feedback === "up"} aria-label="Good answer: save it as a test case">👍</Button>
          <Button variant="ghost" className={`${small} ${m.feedback === "down" ? "!bg-bad/20 !text-bad" : ""}`} onClick={() => onRate("down")} aria-pressed={m.feedback === "down"} aria-label="Wrong answer: save the right one as a test case">👎</Button>
          <Button variant="ghost" className={small} onClick={onSave} aria-expanded={saving}>{saving ? "Hide form" : "Save as test case"}</Button>
        </div>
      )}
    </div>
  );
}

/** Turns a chat exchange into a permanent benchmark question (POST /questions). */
function SaveCase({ domain, mode, question, answer, onClose }: { domain: string; mode: SaveMode; question: string; answer: string; onClose: () => void }) {
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
      <h2 className="mb-1 text-sm font-semibold">{mode === "down" ? "This answer was wrong: save the right one" : "Save as a benchmark test case"}</h2>
      <p className="mb-4 text-xs text-muted">
        {mode === "down"
          ? "Write the answer the chatbot should have given. Future benchmark runs will check against it, so a mistake like this can't come back unnoticed. "
          : ""}
        Test questions are asked on their own, without the chat history, so write the question so it makes sense by itself.
      </p>
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
            <textarea id="st" rows={3} required maxLength={2000} className={inputCls} value={truth} onChange={(e) => setTruth(e.target.value)} placeholder={mode === "down" ? "The correct answer, as the documents state it" : undefined} />
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
