"use client";

import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useFetch } from "@/lib/api";
import type { Domain, Run, Status } from "@/lib/types";

export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
export const fmtDate = (ts: string) => new Date(ts + (ts.endsWith("Z") ? "" : "Z")).toLocaleString();

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/** `delay` (0-based) staggers the entrance of sibling cards; only use it on the first screenful. */
export function Card({ title, children, className = "", delay }: { title?: string; children: ReactNode; className?: string; delay?: number }) {
  return (
    <section className={`glass p-5 ${delay !== undefined ? "rise" : ""} ${className}`} style={delay !== undefined ? ({ "--i": delay } as React.CSSProperties) : undefined}>
      {title && <h2 className="mb-3 text-sm font-semibold">{title}</h2>}
      {children}
    </section>
  );
}

/** Counts up from 0 to the numeric part of `value` (e.g. "93.8%", "2311 ms") once, then stays put. */
function CountUp({ value }: { value: string }) {
  const m = /^(-?\d+(?:\.\d+)?)(.*)$/.exec(value);
  const target = m ? parseFloat(m[1]) : null;
  const decimals = m && m[1].includes(".") ? m[1].split(".")[1].length : 0;
  const [shown, setShown] = useState<number | null>(null);
  const prev = useRef(0);

  useEffect(() => {
    if (target === null) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      prev.current = target;
      return;
    }
    const from = prev.current;
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 750);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(from + (target - from) * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
      else prev.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  if (!m || target === null) return <>{value}</>;
  // `value` is the source of truth for the final text; the animated number only drives the in-between frames
  return <>{shown === null || shown === target ? value : `${shown.toFixed(decimals)}${m[2]}`}</>;
}

export function Stat({ label, value, hint, tone, delay }: { label: string; value: string; hint?: string; tone?: "good" | "warn" | "bad"; delay?: number }) {
  const color = tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "";
  return (
    <div className={`glass p-4 ${delay !== undefined ? "rise" : ""}`} style={delay !== undefined ? ({ "--i": delay } as React.CSSProperties) : undefined}>
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={`mt-1 text-[1.65rem] font-semibold leading-tight tabular-nums ${color}`}>
        <CountUp value={value} />
      </div>
      {hint && <div className="mt-1 truncate text-xs text-muted">{hint}</div>}
    </div>
  );
}

export const statusTone = (s: string) => (s === "done" ? "good" : s === "failed" ? "bad" : "accent") as "good" | "bad" | "accent";

export function scoreTone(v: number, threshold = 0.75): "good" | "warn" | "bad" {
  return v >= threshold ? "good" : v >= threshold - 0.15 ? "warn" : "bad";
}

export function Badge({ children, tone = "neutral", title }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "accent"; title?: string }) {
  const tones = {
    neutral: "bg-surface-2 text-muted",
    good: "bg-good/15 text-good",
    warn: "bg-warn/15 text-warn",
    bad: "bg-bad/15 text-bad",
    accent: "bg-accent/15 text-accent",
  };
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** A status dot that pulses while something is in progress. */
export function LiveDot() {
  return <span aria-hidden className="live-dot inline-block size-1.5 rounded-full bg-current" />;
}

export function ScorerBadge({ run }: { run: Pick<Run, "scorer" | "is_simulated"> }) {
  const s = run.scorer;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {run.is_simulated ? <Badge tone="warn" title="Synthetic degraded run created by the drift simulator">simulated</Badge> : null}
      {!s ? (
        <Badge title="Created before scorer tracking">unknown scorer</Badge>
      ) : s.includes("mock") ? (
        <Badge tone="bad" title="Hard-coded mock judge: scores are not real measurements">mock</Badge>
      ) : s.includes("heuristic") ? (
        <Badge tone="warn" title="Lexical heuristic fallback was used for some or all scores">{s}</Badge>
      ) : (
        <Badge tone="good" title={`LLM judge ${s}`}>LLM judge</Badge>
      )}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2.5 py-8 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-border border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="glass rise border-bad/40 p-4 text-sm" style={{ background: "color-mix(in srgb, var(--bad) 10%, var(--glass))" }}>
      <div className="font-semibold text-bad">Something went wrong</div>
      <div className="mt-1 break-words">{message}</div>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry} className="mt-3 !px-3 !py-1.5 text-xs">
          Retry
        </Button>
      )}
    </div>
  );
}

export function Empty({ title, hint, href, cta }: { title: string; hint?: string; href?: string; cta?: string }) {
  return (
    <div className="glass rise p-10 text-center">
      <div className="font-semibold">{title}</div>
      {hint && <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">{hint}</p>}
      {href && (
        <Link href={href} className="btn-primary btn-spring mt-5 inline-block rounded-full px-5 py-2 text-sm font-medium text-white">
          {cta}
        </Link>
      )}
    </div>
  );
}

export function Button({ children, variant = "primary", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const base = "btn-spring inline-flex items-center justify-center gap-2 rounded-full px-5 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50";
  const v = variant === "primary" ? "btn-primary text-white" : "glass-inset hover:bg-surface";
  return (
    <button {...rest} className={`${base} ${v} ${rest.className ?? ""}`}>
      {children}
    </button>
  );
}

export const inputCls = "glass-inset w-full rounded-2xl px-3.5 py-2.5 text-sm placeholder:text-muted";

/** Red banner whenever the backend is using the mock LLM, so fake numbers are never mistaken for real ones. */
export function MockBanner() {
  const { data } = useFetch<Status>("/status");
  if (!data?.is_mock) return null;
  return (
    <div role="alert" className="glass rise mb-6 p-3.5 text-sm" style={{ background: "color-mix(in srgb, var(--bad) 12%, var(--glass))" }}>
      <strong className="text-bad">Mock LLM active.</strong> Judge scores are hard-coded constants, not real measurements. Set
      <code className="mx-1 rounded-md bg-surface-2 px-1.5">LLM_PROVIDER=openrouter</code> and an API key in the backend <code className="rounded-md bg-surface-2 px-1.5">.env</code>.
    </div>
  );
}

/** key -> Domain metadata. */
export function useDomains() {
  const { data, ...rest } = useFetch<{ domains: Domain[] }>("/domains");
  const byKey: Record<string, Domain> = Object.fromEntries((data?.domains ?? []).map((d) => [d.key, d]));
  return { domains: data?.domains ?? [], byKey, ...rest };
}

export function domainLabel(byKey: Record<string, Domain>, key: string) {
  const d = byKey[key];
  return d ? `${d.icon} ${d.name}` : key;
}
