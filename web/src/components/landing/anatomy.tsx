"use client";

import { useState, type CSSProperties } from "react";

/* One evaluated answer, taken apart. The good/bad toggle shows how the marks change. Figures are illustrative. */

const CASES = {
  good: {
    answer: "Full-time employees get 18 days of PTO per year, accruing 1.5 days for each completed calendar month.",
    faith: 100, rel: 100,
    reason: "Both figures match the document: 18 days a year and 1.5 days a month. Nothing was added.",
    verdict: "Passes",
    tone: "text-good",
  },
  bad: {
    answer: "Employees receive 20 days of PTO per year, accruing 2 days every month.",
    faith: 0, rel: 10,
    reason: "Unsupported: the document says 18 days and 1.5 days per month, not 20 and 2. The right page was found, but the answer does not follow it.",
    verdict: "Fails",
    tone: "text-bad",
  },
} as const;

function Bar({ label, value, hint }: { label: string; value: number; hint: string }) {
  const tone = value >= 75 ? "bg-good" : value >= 50 ? "bg-warn" : "bg-bad";
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums font-semibold">{value}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-surface-2" role="meter" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className={`bar-grow h-full rounded-full ${tone}`} style={{ width: `${Math.max(value, 2)}%` } as CSSProperties} />
      </div>
      <p className="mt-1 text-xs text-muted">{hint}</p>
    </div>
  );
}

export function AnswerAnatomy() {
  const [mode, setMode] = useState<"good" | "bad">("good");
  const c = CASES[mode];

  return (
    <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
      <div className="glass grid content-start gap-4 p-5 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold">Anatomy of one answer</h3>
          <div role="radiogroup" aria-label="Which answer to show" className="glass-inset inline-flex rounded-full p-1 text-sm">
            {(["good", "bad"] as const).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                className={`rounded-full px-4 py-1.5 font-medium transition-all duration-300 ${mode === m ? "glass-pill-active text-foreground" : "text-muted"}`}>
                {m === "good" ? "A good answer" : "A bad answer"}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 text-sm">
          <div className="rounded-2xl bg-surface-2 p-3.5">
            <div className="mb-0.5 text-xs font-semibold text-muted">1. The test question</div>
            How many days of annual PTO do employees receive, and what is the monthly accrual rate?
          </div>
          <div className="rounded-2xl bg-surface-2 p-3.5">
            <div className="mb-0.5 text-xs font-semibold text-muted">2. What the search found (from the HR document)</div>
            Full-time employees receive eighteen (18) days of Paid Time Off (PTO) per calendar year, accrued at 1.5 days per completed calendar month of active service.
          </div>
          <div key={mode} className={`panel-in rounded-2xl p-3.5 ${mode === "good" ? "bg-good/12" : "bg-bad/12"}`}>
            <div className="mb-0.5 text-xs font-semibold text-muted">3. What the chatbot answered</div>
            {c.answer}
          </div>
        </div>
      </div>

      <div className="glass grid content-start gap-4 p-5 md:p-6" key={`scores-${mode}`}>
        <h3 className="font-semibold">4. What the judge decided <span className={`ml-1 text-sm ${c.tone}`}>{c.verdict}</span></h3>
        <Bar label="Faithfulness" value={c.faith} hint="Did it stick to the document text?" />
        <Bar label="Relevance" value={c.rel} hint="Did it give the right facts?" />
        <Bar label="Search quality" value={100} hint="The right page was found in both cases." />
        <div className="rounded-2xl bg-surface-2 p-3.5 text-sm">
          <div className="mb-0.5 text-xs font-semibold text-muted">The judge’s written reason</div>
          {c.reason}
        </div>
        <p className="text-xs text-muted">Illustrative example based on the HR benchmark document. In the app, every real answer shows its own reason like this one.</p>
      </div>
    </div>
  );
}
