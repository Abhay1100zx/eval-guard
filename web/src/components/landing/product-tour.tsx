"use client";

import { useRef, useState, type CSSProperties, type KeyboardEvent } from "react";

/* An interactive tour of the app. Panels are built from sample data (labelled as such), not live results. */

const TABS = [
  { id: "overview", label: "Overview", blurb: "Quality for every industry at a glance, and how it has moved over time." },
  { id: "run", label: "Run detail", blurb: "Every question, the document pieces found, the answer, and the judge’s reasons." },
  { id: "drift", label: "Drift lab", blurb: "Two runs side by side. A statistical test says whether the drop is real." },
  { id: "experiment", label: "Experiments", blurb: "The same questions through two prompts or models, compared question by question." },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Pill({ tone = "neutral", children }: { tone?: "neutral" | "good" | "warn" | "bad" | "accent"; children: React.ReactNode }) {
  const t = { neutral: "bg-surface-2 text-muted", good: "bg-good/15 text-good", warn: "bg-warn/15 text-warn", bad: "bg-bad/15 text-bad", accent: "bg-accent/15 text-accent" }[tone];
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${t}`}>{children}</span>;
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  const c = tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "";
  return (
    <div className="glass-inset rounded-2xl p-3">
      <div className="text-[11px] font-medium text-muted">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${c}`}>{value}</div>
    </div>
  );
}

/* ───────────── Overview ───────────── */
const series: { name: string; color: string; vals: number[] }[] = [
  { name: "Faithfulness", color: "var(--good)", vals: [90, 92, 91, 93, 92, 94, 93, 94] },
  { name: "Relevance", color: "var(--accent)", vals: [86, 88, 87, 90, 89, 91, 90, 92] },
  { name: "Hit rate", color: "var(--warn)", vals: [82, 84, 85, 84, 86, 87, 86, 87] },
];
const pts = (vals: number[]) => vals.map((v, i) => `${24 + i * 68},${130 - (v - 60) * 3}`).join(" ");

function OverviewPanel() {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Tile label="Faithfulness" value="94.1%" tone="good" />
        <Tile label="Relevance" value="91.7%" tone="good" />
        <Tile label="Hit rate" value="86.7%" tone="good" />
        <Tile label="Safety" value="100%" tone="good" />
      </div>
      <div className="glass-inset rounded-2xl p-3">
        <div className="mb-1 flex flex-wrap items-center gap-3 text-xs">
          <span className="font-semibold">Quality over time</span>
          {series.map((s) => (
            <span key={s.name} className="inline-flex items-center gap-1.5 text-muted"><i className="inline-block size-2 rounded-full" style={{ background: s.color }} />{s.name}</span>
          ))}
        </div>
        <svg viewBox="0 0 520 150" className="dg block h-auto w-full" role="img" aria-label="Sample line chart of three quality scores rising slowly across eight runs">
          {[40, 70, 100, 130].map((y) => <line key={y} className="grid" x1="24" y1={y} x2="500" y2={y} />)}
          {series.map((s) => (
            <polyline key={s.name} pathLength={1} className="draw" fill="none" stroke={s.color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" points={pts(s.vals)} />
          ))}
        </svg>
      </div>
      <div className="glass-inset divide-y divide-border rounded-2xl text-sm">
        {[
          ["HR benchmark", "LLM judge", "94.2%", "91.8%"],
          ["Legal benchmark", "LLM judge", "92.6%", "90.4%"],
          ["IT Support benchmark", "LLM judge", "95.1%", "93.0%"],
        ].map(([n, b, f, r]) => (
          <div key={n} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2">
            <span className="font-medium">{n}</span><Pill tone="good">{b}</Pill>
            <span className="ml-auto tabular-nums text-muted">faith {f} · rel {r}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────── Run detail ───────────── */
function RunPanel() {
  const rows: [string, string, string, string, "good" | "warn"][] = [
    ["What is the maximum number of unused PTO days that can roll over?", "1.00", "1.00", "retrieved", "good"],
    ["How much paid parental leave does a primary caregiver receive?", "0.50", "0.75", "retrieved", "warn"],
  ];
  return (
    <div className="grid gap-2.5 text-sm">
      <div className="glass-inset rounded-2xl">
        <div className="flex flex-wrap items-center gap-2 p-3">
          <span aria-hidden>✅</span>
          <span className="min-w-0 flex-1 font-medium">How many days of annual PTO do employees receive, and at what monthly rate?</span>
          <Pill tone="good">faith 1.00</Pill><Pill tone="good">rel 1.00</Pill><Pill tone="good">retrieved</Pill>
        </div>
        <div className="grid gap-3 border-t border-border p-3 md:grid-cols-2">
          <div><div className="mb-0.5 text-[11px] font-medium text-muted">Expected</div>Full-time employees receive 18 days of PTO a year, accruing 1.5 days per completed month.</div>
          <div><div className="mb-0.5 text-[11px] font-medium text-muted">Chatbot answered</div>Employees get 18 days of PTO per year, accrued at 1.5 days for each completed calendar month.</div>
          <div className="rounded-xl bg-good/10 p-2.5 md:col-span-2"><div className="mb-0.5 text-[11px] font-medium text-muted">Judge’s reasoning</div>Both figures match the document: 18 days a year and 1.5 days a month. Nothing was added that the document does not say.</div>
          <div className="rounded-xl bg-surface-2 p-2.5 md:col-span-2"><div className="mb-0.5 text-[11px] font-medium text-muted">Document piece found · similarity 0.71</div>Full-time employees receive eighteen (18) days of Paid Time Off (PTO) per calendar year, accrued at 1.5 days per completed calendar month of active service.</div>
        </div>
      </div>
      {rows.map(([q, f, r, h, t]) => (
        <div key={q} className="glass-inset flex flex-wrap items-center gap-2 rounded-2xl p-3">
          <span aria-hidden>{t === "good" ? "✅" : "⚠️"}</span>
          <span className="min-w-0 flex-1">{q}</span>
          <Pill tone={t}>faith {f}</Pill><Pill tone={t}>rel {r}</Pill><Pill tone="good">{h}</Pill>
        </div>
      ))}
      <div className="glass-inset flex flex-wrap items-center gap-2 rounded-2xl p-3">
        <span aria-hidden>✅</span>
        <span className="min-w-0 flex-1">How much is the dental plan premium?</span>
        <Pill tone="accent">out of scope</Pill><Pill tone="good">safe</Pill>
      </div>
    </div>
  );
}

/* ───────────── Drift ───────────── */
const baseBars = [1, 1, 2, 3, 5, 8, 12, 9, 4, 2];
const candBars = [3, 7, 10, 8, 5, 3, 1, 1, 0, 0];

function DriftPanel() {
  const cards: [string, string, string, string, "bad" | "warn" | "good"][] = [
    ["Faithfulness", "0.61", "−0.32 vs 0.93", "KS 0.84 · p 0.0003", "bad"],
    ["Relevance", "0.55", "−0.35 vs 0.90", "KS 0.88 · p 0.0001", "bad"],
    ["Hit rate", "0.83", "−0.04 vs 0.87", "KS 0.20 · p 0.62", "warn"],
    ["Latency", "2.4 s", "+0.1 s vs 2.3 s", "KS 0.12 · p 0.91", "good"],
  ];
  const label = { bad: "drift", warn: "warning", good: "stable" } as const;
  return (
    <div className="grid gap-3">
      <div className="rounded-2xl border border-bad/40 bg-bad/10 p-3 text-sm">
        <div className="font-semibold">🚨 Drift detected</div>
        <p className="mt-0.5 text-muted">Metric distribution shift detected. Review prompt changes, chunking, or model updates.</p>
      </div>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {cards.map(([n, v, d, k, t]) => (
          <div key={n} className="glass-inset rounded-2xl p-3">
            <div className="flex items-center justify-between text-sm"><span className="font-medium">{n}</span><Pill tone={t}>{label[t]}</Pill></div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{v}</div>
            <div className={`text-xs tabular-nums ${t === "bad" ? "text-bad" : "text-muted"}`}>{d}</div>
            <div className="text-xs text-muted">{k}</div>
          </div>
        ))}
      </div>
      <div className="glass-inset rounded-2xl p-3">
        <div className="mb-2 flex items-center gap-4 text-xs"><span className="font-semibold">Faithfulness: score distribution</span><span className="inline-flex items-center gap-1.5 text-muted"><i className="inline-block size-2 rounded-full bg-muted" />Baseline</span><span className="inline-flex items-center gap-1.5 text-muted"><i className="inline-block size-2 rounded-full bg-accent" />Candidate</span></div>
        <div className="flex h-24 items-end gap-1.5" role="img" aria-label="Sample histogram: baseline scores bunch at the high end, candidate scores bunch at the low end">
          {baseBars.map((b, i) => (
            <div key={i} className="flex h-full flex-1 items-end gap-0.5">
              <div className="col-grow w-1/2 rounded-t bg-muted/70" style={{ height: `${b * 8}%`, "--i": i } as CSSProperties} />
              <div className="col-grow w-1/2 rounded-t bg-accent" style={{ height: `${candBars[i] * 9}%`, "--i": i + 3 } as CSSProperties} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ───────────── Experiments ───────────── */
function ExperimentPanel() {
  const rows = [
    ["Strict (default)", "Default (strict, grounded)", "94.7%", "91.0%", "88.0%", "100%", "2.6 s", false],
    ["Concise", "Concise", "91.3%", "88.7%", "88.0%", "80.0%", "1.9 s", true],
  ] as const;
  return (
    <div className="grid gap-3 text-sm">
      <div className="rounded-2xl border border-good/40 bg-good/10 p-3"><strong>Strict (default)</strong> scored highest overall (95.2%), 8.6 points ahead of Concise.</div>
      <div className="glass-inset overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[520px] text-left">
          <thead className="text-[11px] text-muted"><tr><th className="px-3 py-2 font-medium">Variant</th><th className="px-3 py-2 font-medium">Faith.</th><th className="px-3 py-2 font-medium">Rel.</th><th className="px-3 py-2 font-medium">Hit</th><th className="px-3 py-2 font-medium">Safety</th><th className="px-3 py-2 font-medium">Latency</th></tr></thead>
          <tbody>
            {rows.map(([v, , f, r, h, s, l, fast]) => (
              <tr key={v} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{v}</td>
                <td className={`px-3 py-2 tabular-nums ${!fast ? "font-semibold text-good" : ""}`}>{f}{!fast ? " ▲" : ""}</td>
                <td className={`px-3 py-2 tabular-nums ${!fast ? "font-semibold text-good" : ""}`}>{r}{!fast ? " ▲" : ""}</td>
                <td className="px-3 py-2 tabular-nums">{h}</td>
                <td className={`px-3 py-2 tabular-nums ${!fast ? "font-semibold text-good" : ""}`}>{s}{!fast ? " ▲" : ""}</td>
                <td className={`px-3 py-2 tabular-nums ${fast ? "font-semibold text-good" : ""}`}>{l}{fast ? " ▲" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="glass-inset rounded-2xl p-3">
        <div className="font-medium">Question: What is the one-time home office stipend and its deadline?</div>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <div className="rounded-xl bg-surface-2 p-2.5"><div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-semibold text-muted">Strict <Pill tone="good">safe</Pill></div>A one-time reimbursement of $500, submitted within 90 days of hiring.</div>
          <div className="rounded-xl bg-surface-2 p-2.5"><div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-semibold text-muted">Concise <Pill tone="warn">rel 0.60</Pill></div>$500, one time.</div>
        </div>
      </div>
    </div>
  );
}

const PANELS: Record<TabId, () => React.JSX.Element> = { overview: OverviewPanel, run: RunPanel, drift: DriftPanel, experiment: ExperimentPanel };

export function ProductTour() {
  const [active, setActive] = useState<TabId>("overview");
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const Panel = PANELS[active];

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.id === active);
    const next = e.key === "ArrowDown" || e.key === "ArrowRight" ? (i + 1) % TABS.length : e.key === "ArrowUp" || e.key === "ArrowLeft" ? (i + TABS.length - 1) % TABS.length : -1;
    if (next < 0) return;
    e.preventDefault();
    setActive(TABS[next].id);
    refs.current[TABS[next].id]?.focus();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <div role="tablist" aria-label="Product tour" aria-orientation="vertical" onKeyDown={onKey} className="grid content-start gap-2 sm:grid-cols-2 lg:grid-cols-1">
        {TABS.map((t) => {
          const on = t.id === active;
          return (
            <button
              key={t.id} ref={(el) => { refs.current[t.id] = el; }} role="tab" id={`tab-${t.id}`} aria-selected={on} aria-controls="tour-panel" tabIndex={on ? 0 : -1}
              onClick={() => setActive(t.id)}
              className={`btn-spring rounded-2xl p-4 text-left transition-colors ${on ? "glass-pill-active" : "glass-inset text-muted hover:text-foreground"}`}
            >
              <span className={`block font-semibold ${on ? "text-foreground" : ""}`}>{t.label}</span>
              <span className="mt-0.5 block text-sm leading-snug text-muted">{t.blurb}</span>
            </button>
          );
        })}
      </div>

      <div className="glass-strong overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <i className="size-2.5 rounded-full bg-bad/70" /><i className="size-2.5 rounded-full bg-warn/70" /><i className="size-2.5 rounded-full bg-good/70" />
          <span className="ml-3 text-xs text-muted">EvalGuard · {TABS.find((t) => t.id === active)?.label}</span>
          <span className="ml-auto"><Pill>Sample data</Pill></span>
        </div>
        <div key={active} id="tour-panel" role="tabpanel" aria-labelledby={`tab-${active}`} className="panel-in p-4 md:p-5">
          <Panel />
        </div>
      </div>
    </div>
  );
}
