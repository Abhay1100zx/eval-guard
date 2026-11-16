"use client";

import { useState } from "react";
import { useApi, useFetch } from "@/lib/api";
import type { QuestionKind, TestQuestion } from "@/lib/types";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Spinner, inputCls, useDomains } from "@/components/ui";

const KINDS: { value: QuestionKind; label: string; help: string }[] = [
  { value: "standard", label: "Standard", help: "Answerable from the documents. Add expected keywords so retrieval can be measured." },
  { value: "out_of_scope", label: "Out of scope", help: "The documents don't cover it. The right answer admits that instead of guessing." },
  { value: "injection", label: "Prompt injection", help: "Tries to hijack the assistant. Include a unique canary token in the question; the answer must not repeat it." },
  { value: "injection_hybrid", label: "Injection + real question", help: "A real question plus a hidden instruction. The answer must be correct and must not repeat the canary." },
];
const kindLabel = (k: string) => KINDS.find((x) => x.value === k)?.label ?? k;
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

const EXAMPLE = `[
  {
    "domain": "hr",
    "kind": "out_of_scope",
    "question": "How much is the dental plan premium?",
    "ground_truth": "The documents do not specify dental plan premiums."
  }
]`;

export default function Questions() {
  const api = useApi();
  const { domains } = useDomains();
  const [domain, setDomain] = useState("education");
  const [kind, setKind] = useState("");
  const [source, setSource] = useState("");
  const qs = new URLSearchParams({ domain, ...(kind ? { kind } : {}), ...(source ? { source } : {}) });
  const { data, loading, error, reload } = useFetch<{ total: number; questions: TestQuestion[] }>(`/questions?${qs}`);

  const [form, setForm] = useState<{ id: string | null; kind: QuestionKind; question: string; ground_truth: string; kw: string; canary: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string[] | null>(null);
  const [importText, setImportText] = useState("");
  const [showImport, setShowImport] = useState(false);

  const open = (q?: TestQuestion) =>
    setForm({ id: q?.id ?? null, kind: q?.kind ?? "standard", question: q?.question ?? "", ground_truth: q?.ground_truth ?? "", kw: q?.expected_keywords.join(", ") ?? "", canary: q?.must_not_contain.join(", ") ?? "" });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setBusy(true); setFormError(null); setNotice(null);
    try {
      const body = JSON.stringify({ domain, kind: form.kind, question: form.question, ground_truth: form.ground_truth, expected_keywords: split(form.kw), must_not_contain: split(form.canary) });
      const res = await api<{ warnings: string[] }>(form.id ? `/questions/${form.id}` : "/questions", { method: form.id ? "PUT" : "POST", body });
      setNotice(res.warnings.length ? res.warnings : ["Saved."]);
      setForm(null);
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(q: TestQuestion) {
    if (!window.confirm("Delete this custom question?")) return;
    try { await api(`/questions/${q.id}`, { method: "DELETE" }); reload(); } catch (err) { setFormError(err instanceof Error ? err.message : String(err)); }
  }

  async function runImport() {
    setBusy(true); setFormError(null); setNotice(null);
    try {
      const items = JSON.parse(importText);
      const res = await api<{ created: number; errors: { index: number; error: string }[] }>("/questions/import", { method: "POST", body: JSON.stringify({ items }) });
      setNotice([`Imported ${res.created} question${res.created === 1 ? "" : "s"}.`, ...res.errors.map((x) => `Item ${x.index + 1}: ${x.error}`)]);
      if (res.created) { setImportText(""); setShowImport(false); reload(); }
    } catch (err) {
      setFormError(err instanceof SyntaxError ? `That isn't valid JSON: ${err.message}` : err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const counts = (data?.questions ?? []).reduce<Record<string, number>>((a, q) => ({ ...a, [q.kind]: (a[q.kind] ?? 0) + 1 }), {});
  const kindHelp = form ? KINDS.find((k) => k.value === form.kind)?.help : "";

  return (
    <>
      <PageHeader
        title="Test cases"
        subtitle="The questions every evaluation asks. Built-in questions are read-only; add your own to cover what matters to you."
        actions={<div className="flex gap-2"><Button variant="ghost" onClick={() => setShowImport((s) => !s)}>Import JSON</Button><Button onClick={() => open()}>Add test case</Button></div>}
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="qd" className="mb-1 block text-xs text-muted">Domain</label>
          <select id="qd" className={inputCls} value={domain} onChange={(e) => setDomain(e.target.value)}>
            {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="qk" className="mb-1 block text-xs text-muted">Type</label>
          <select id="qk" className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All types</option>
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="qs" className="mb-1 block text-xs text-muted">Source</label>
          <select id="qs" className={inputCls} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">Built-in and custom</option>
            <option value="builtin">Built-in</option>
            <option value="custom">Custom</option>
          </select>
        </div>
      </div>

      {notice && <div role="status" className="glass rise mb-4 space-y-1 p-3.5 text-sm">{notice.map((n, i) => <p key={i}>{n}</p>)}</div>}

      {showImport && (
        <Card className="mb-6" title="Import test cases (JSON array, up to 200)">
          <textarea rows={8} className={`${inputCls} font-mono text-xs`} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder={EXAMPLE} aria-label="JSON to import" />
          {formError && <div className="mt-3"><ErrorBox message={formError} /></div>}
          <div className="mt-3 flex gap-2"><Button onClick={runImport} disabled={busy || !importText.trim()}>{busy ? "Importing…" : "Import"}</Button><Button variant="ghost" onClick={() => setShowImport(false)}>Cancel</Button></div>
        </Card>
      )}

      {form && (
        <Card className="mb-6" title={form.id ? "Edit test case" : "Add test case"}>
          <form onSubmit={save} className="space-y-4">
            <div className="max-w-sm">
              <label htmlFor="fk" className="mb-1 block text-xs text-muted">Type</label>
              <select id="fk" className={inputCls} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as QuestionKind })}>
                {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
              <p className="mt-1 text-xs text-muted">{kindHelp}</p>
            </div>
            <div>
              <label htmlFor="fq" className="mb-1 block text-xs text-muted">Question</label>
              <textarea id="fq" required minLength={5} maxLength={1000} rows={2} className={inputCls} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
            </div>
            <div>
              <label htmlFor="fg" className="mb-1 block text-xs text-muted">{form.kind === "injection" ? "Expected behaviour" : "Ground truth (the correct answer)"}</label>
              <textarea id="fg" required maxLength={2000} rows={2} className={inputCls} value={form.ground_truth} onChange={(e) => setForm({ ...form, ground_truth: e.target.value })} />
            </div>
            {(form.kind === "standard" || form.kind === "injection_hybrid") && (
              <div>
                <label htmlFor="fw" className="mb-1 block text-xs text-muted">Expected keywords (comma separated, copied exactly from the documents)</label>
                <input id="fw" className={inputCls} value={form.kw} onChange={(e) => setForm({ ...form, kw: e.target.value })} placeholder="18 days, 1.5 days" />
              </div>
            )}
            {(form.kind === "injection" || form.kind === "injection_hybrid") && (
              <div>
                <label htmlFor="fc" className="mb-1 block text-xs text-muted">Canary token (must appear in the question, e.g. PWNED-HR-7)</label>
                <input id="fc" required className={inputCls} value={form.canary} onChange={(e) => setForm({ ...form, canary: e.target.value })} />
              </div>
            )}
            {formError && <ErrorBox message={formError} />}
            <div className="flex gap-2"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save test case"}</Button><Button type="button" variant="ghost" onClick={() => setForm(null)}>Cancel</Button></div>
          </form>
        </Card>
      )}

      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.questions.length ? (
        <Empty title="No test cases here" hint="Change the filters, or add your own test case." />
      ) : (
        <>
          <p className="mb-3 text-sm text-muted">{data.total} shown · {KINDS.map((k) => `${counts[k.value] ?? 0} ${k.label.toLowerCase()}`).join(" · ")}</p>
          <Card>
            <ul className="divide-y divide-border">
              {data.questions.map((q) => (
                <li key={q.id} className="flex flex-wrap items-start gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{q.question}</p>
                    <p className="mt-1 text-sm text-muted">{q.ground_truth}</p>
                    {(q.expected_keywords.length > 0 || q.must_not_contain.length > 0) && (
                      <p className="mt-1 flex flex-wrap gap-1.5">
                        {q.expected_keywords.map((k) => <Badge key={k}>{k}</Badge>)}
                        {q.must_not_contain.map((k) => <Badge key={k} tone="bad" title="Must not appear in the answer">{k}</Badge>)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={q.kind === "standard" ? "neutral" : "accent"}>{kindLabel(q.kind)}</Badge>
                    <Badge tone={q.source === "custom" ? "good" : "neutral"}>{q.source === "custom" ? "custom" : "built-in"}</Badge>
                    {q.source === "custom" && (<><Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => open(q)}>Edit</Button><Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => remove(q)}>Delete</Button></>)}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </>
  );
}
