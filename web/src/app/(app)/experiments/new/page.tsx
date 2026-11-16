"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useApi, useFetch } from "@/lib/api";
import type { PromptVersion, Status } from "@/lib/types";
import { Button, Card, ErrorBox, MockBanner, PageHeader, inputCls, useDomains } from "@/components/ui";

interface Variant { label: string; prompt_id: string; model: string }

const SECONDS_PER_QUESTION = 20; // free models: answer + two judge calls, with rate-limit retries

export default function NewExperiment() {
  const api = useApi();
  const router = useRouter();
  const params = useSearchParams();
  const { domains } = useDomains();
  const prompts = useFetch<{ prompts: PromptVersion[] }>("/prompts");
  const models = useFetch<{ models: { id: string; name: string }[]; provider: string }>("/models/free");
  const status = useFetch<Status>("/status");

  const [kind, setKind] = useState<"prompt" | "model">(params.get("kind") === "model" ? "model" : "prompt");
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("education");
  const [suite, setSuite] = useState("standard");
  const [limit, setLimit] = useState(8);
  const [sharedPrompt, setSharedPrompt] = useState("");
  const [variants, setVariants] = useState<Variant[]>([
    { label: "A", prompt_id: "", model: "" },
    { label: "B", prompt_id: "", model: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const plist = prompts.data?.prompts ?? [];
  const defaultPrompt = plist.find((p) => p.is_default)?.id ?? "";
  // Pre-fill sensible defaults without an effect: an unset prompt means "default" / "the configured answer model"
  const effective = (v: Variant, i: number): Variant => ({
    ...v,
    prompt_id: v.prompt_id || (i === 0 ? defaultPrompt : (plist.find((p) => !p.is_default)?.id ?? defaultPrompt)),
    model: v.model || (i === 0 ? (status.data?.answer_model ?? "") : ""),
  });
  const rows = variants.map(effective);
  const minutes = Math.max(1, Math.round((rows.length * limit * SECONDS_PER_QUESTION) / 60));

  const setRow = (i: number, patch: Partial<Variant>) =>
    setVariants((vs) => vs.map((v, j) => (j === i ? { ...effective(v, i), ...patch } : v)));
  const addRow = () => setVariants((vs) => (vs.length < 5 ? [...vs, { label: String.fromCharCode(65 + vs.length), prompt_id: "", model: "" }] : vs));
  const removeRow = (i: number) => setVariants((vs) => (vs.length > 2 ? vs.filter((_, j) => j !== i) : vs));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: name || `${kind === "prompt" ? "Prompt" : "Model"} comparison`,
        kind, domain, suite, question_limit: limit,
        prompt_id: kind === "model" ? sharedPrompt || defaultPrompt : undefined,
        variants: rows.map((v) => (kind === "prompt" ? { label: v.label, prompt_id: v.prompt_id } : { label: v.label, model: v.model })),
      };
      const r = await api<{ experiment_id: string; job_id: string }>("/experiments", { method: "POST", body: JSON.stringify(body) });
      router.push(`/experiments/${r.experiment_id}?job=${r.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const modelOptions = models.data?.models ?? [];

  return (
    <>
      <PageHeader title="New experiment" subtitle="Every variant answers the same questions and is judged by the same judge model, so differences come from what you changed." />
      <MockBanner />
      <form onSubmit={submit} className="space-y-6">
        <Card title="What do you want to compare?">
          <div role="radiogroup" aria-label="Experiment type" className="glass-inset inline-flex rounded-full p-1">
            {(["prompt", "model"] as const).map((k) => (
              <button
                key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                className={`rounded-full px-5 py-1.5 text-sm font-medium transition-all duration-300 ${kind === k ? "glass-pill-active" : "text-muted"}`}
              >
                {k === "prompt" ? "Prompts" : "Models"}
              </button>
            ))}
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="en" className="mb-1 block text-xs text-muted">Experiment name</label>
              <input id="en" maxLength={120} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={kind === "prompt" ? "e.g. Concise vs strict, HR" : "e.g. Ernie vs Gemma, HR"} />
            </div>
            <div>
              <label htmlFor="ed" className="mb-1 block text-xs text-muted">Domain</label>
              <select id="ed" className={inputCls} value={domain} onChange={(e) => setDomain(e.target.value)}>
                {domains.map((d) => <option key={d.key} value={d.key}>{d.icon} {d.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="es" className="mb-1 block text-xs text-muted">Question set</label>
              <select id="es" className={inputCls} value={suite} onChange={(e) => setSuite(e.target.value)}>
                <option value="standard">Standard questions</option>
                <option value="adversarial">Adversarial / safety tests</option>
                <option value="all">Both</option>
              </select>
            </div>
            <div>
              <label htmlFor="el" className="mb-1 block text-xs text-muted">Questions per variant (evenly sampled)</label>
              <input id="el" type="number" min={1} max={60} className={inputCls} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} />
            </div>
          </div>
          {kind === "model" && (
            <div className="mt-4 max-w-md">
              <label htmlFor="sp" className="mb-1 block text-xs text-muted">Prompt used by every model</label>
              <select id="sp" className={inputCls} value={sharedPrompt || defaultPrompt} onChange={(e) => setSharedPrompt(e.target.value)}>
                {plist.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
        </Card>

        <Card title={kind === "prompt" ? "Prompt variants" : "Model variants"}>
          <div className="space-y-3">
            {rows.map((v, i) => (
              <div key={i} className="grid items-end gap-3 md:grid-cols-[10rem_1fr_auto]">
                <div>
                  <label htmlFor={`vl${i}`} className="mb-1 block text-xs text-muted">Label</label>
                  <input id={`vl${i}`} required maxLength={60} className={inputCls} value={v.label} onChange={(e) => setRow(i, { label: e.target.value })} />
                </div>
                {kind === "prompt" ? (
                  <div>
                    <label htmlFor={`vp${i}`} className="mb-1 block text-xs text-muted">Prompt</label>
                    <select id={`vp${i}`} className={inputCls} value={v.prompt_id} onChange={(e) => setRow(i, { prompt_id: e.target.value })}>
                      {plist.map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_default ? " (default)" : ""}</option>)}
                    </select>
                  </div>
                ) : (
                  <div>
                    <label htmlFor={`vm${i}`} className="mb-1 block text-xs text-muted">Model (free OpenRouter models, or type an id)</label>
                    <input id={`vm${i}`} required list="free-models" className={inputCls} value={v.model} onChange={(e) => setRow(i, { model: e.target.value })} placeholder="vendor/model:free" />
                  </div>
                )}
                <Button type="button" variant="ghost" className="!px-3" onClick={() => removeRow(i)} disabled={rows.length <= 2} aria-label={`Remove variant ${v.label}`}>Remove</Button>
              </div>
            ))}
          </div>
          <datalist id="free-models">{modelOptions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</datalist>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button type="button" variant="ghost" onClick={addRow} disabled={rows.length >= 5}>Add variant</Button>
            {kind === "prompt" && plist.length < 2 && <span className="text-xs text-warn">You only have one prompt. Create another on the Prompts page first.</span>}
            {kind === "model" && models.data && models.data.provider !== "openrouter" && <span className="text-xs text-warn">Model comparison needs LLM_PROVIDER=openrouter on the backend.</span>}
          </div>
        </Card>

        {error && <ErrorBox message={error} />}
        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" disabled={busy}>{busy ? "Starting…" : "Start experiment"}</Button>
          <span className="text-sm text-muted">About {minutes} min with free models ({rows.length} variants × {limit} questions). Runs are queued one at a time.</span>
        </div>
      </form>
    </>
  );
}
