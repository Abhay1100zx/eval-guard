"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi, useFetch } from "@/lib/api";
import type { PromptVersion } from "@/lib/types";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Spinner, fmtDate, inputCls } from "@/components/ui";

export default function Prompts() {
  const api = useApi();
  const { data, loading, error, reload } = useFetch<{ prompts: PromptVersion[] }>("/prompts");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function startEdit(p: PromptVersion | null) {
    setEditing(p ? p.id : "new");
    setName(p ? p.name : "");
    setText(p ? p.system_prompt : "");
    setFormError(null);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const body = JSON.stringify({ name, system_prompt: text });
      if (editing === "new") await api("/prompts", { method: "POST", body });
      else await api(`/prompts/${editing}`, { method: "PUT", body });
      setEditing(null);
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(p: PromptVersion) {
    if (!window.confirm(`Delete the prompt "${p.name}"? Past runs keep their results.`)) return;
    try {
      await api(`/prompts/${p.id}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Prompts"
        subtitle="System prompts you can test against the benchmark. Save a variant, then compare it with another in an experiment."
        actions={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => startEdit(null)}>New prompt</Button>
            <Link href="/experiments/new?kind=prompt" className="btn-primary btn-spring inline-flex items-center rounded-full px-5 py-2 text-sm font-medium text-white">Compare prompts</Link>
          </div>
        }
      />

      {editing && (
        <Card className="mb-6" title={editing === "new" ? "New prompt" : "Edit prompt"}>
          <form onSubmit={save} className="space-y-4">
            <div className="max-w-md">
              <label htmlFor="pn" className="mb-1 block text-xs text-muted">Name</label>
              <input id="pn" required maxLength={80} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Concise, cite the source" />
            </div>
            <div>
              <label htmlFor="pt" className="mb-1 block text-xs text-muted">System prompt</label>
              <textarea id="pt" required minLength={10} maxLength={4000} rows={6} className={`${inputCls} font-mono`} value={text} onChange={(e) => setText(e.target.value)} />
              <p className="mt-1 text-xs text-muted">{text.length} / 4000. The retrieved context and question are added after this text, so don&apos;t include them.</p>
            </div>
            {formError && <ErrorBox message={formError} />}
            <div className="flex gap-2">
              <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save prompt"}</Button>
              <Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.prompts.length ? (
        <Empty title="No prompts" hint="Create a prompt to start comparing wording." />
      ) : (
        <div className="space-y-3">
          {data.prompts.map((p, i) => (
            <Card key={p.id} delay={i}>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold">{p.name}</h2>
                {p.is_default ? <Badge tone="accent">default</Badge> : null}
                <span className="text-xs text-muted">{fmtDate(p.created_at)}</span>
                <span className="ml-auto flex gap-2">
                  <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => startEdit(p)}>Edit</Button>
                  {!p.is_default && <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => remove(p)}>Delete</Button>}
                </span>
              </div>
              <pre className="glass-inset mt-3 whitespace-pre-wrap rounded-2xl p-3.5 font-mono text-xs leading-relaxed">{p.system_prompt}</pre>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
