"use client";

import { useState } from "react";
import { useApi } from "@/lib/api";
import { Button, Card, ErrorBox, PageHeader, inputCls, useDomains } from "@/components/ui";

export default function Documents() {
  const api = useApi();
  const { domains } = useDomains();
  const [domain, setDomain] = useState("education");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setDone(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const r = await api<{ saved: string[]; indexed_chunks: number }>(`/domains/${domain}/documents`, { method: "POST", body: fd });
      setDone(`Saved ${r.saved.join(", ")} and re-indexed ${r.indexed_chunks} chunks.`);
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Documents" subtitle="Add .txt, .md or .pdf files (max 10 MB each) to a domain's knowledge base. The domain is re-indexed immediately." />
      <Card>
        <form onSubmit={upload} className="space-y-4">
          <div className="max-w-sm">
            <label htmlFor="d" className="mb-1 block text-xs text-muted">Domain</label>
            <select id="d" className={inputCls} value={domain} onChange={(e) => setDomain(e.target.value)}>
              {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="f" className="mb-1 block text-xs text-muted">Files</label>
            <input id="f" type="file" multiple accept=".txt,.md,.pdf" onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-accent file:px-4 file:py-2 file:text-sm file:font-medium file:text-white" />
          </div>
          <p className="text-xs text-muted">New documents widen the knowledge base but have no benchmark questions of their own, so they won&apos;t change evaluation scores until questions reference them.</p>
          <Button type="submit" disabled={busy || files.length === 0}>{busy ? "Uploading & indexing…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}</Button>
        </form>
      </Card>
      {error && <div className="mt-6"><ErrorBox message={error} /></div>}
      {done && <div role="status" className="glass rise mt-6 p-4 text-sm">{done}</div>}
    </>
  );
}
