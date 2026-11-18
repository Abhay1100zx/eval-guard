"use client";

import { ElementType, ReactNode, useEffect, useRef } from "react";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Scroll-reveal wrapper with an optional pointer spotlight.
 * Content is visible in the server HTML. After hydration, only elements still below the fold are hidden,
 * then revealed (once) as they scroll into view. Nothing is hidden for reduced-motion users.
 */
export function FX({ as = "div", className = "", delay = 0, spot = false, children }: {
  as?: ElementType;
  className?: string;
  delay?: number;
  spot?: boolean;
  children: ReactNode;
}) {
  const Tag = as;
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.92) return; // already on screen: leave it
    el.classList.add("rv-hidden");
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          el.classList.remove("rv-hidden");
          io.disconnect();
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const onMove = spot
    ? (e: React.PointerEvent<HTMLElement>) => {
        const r = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
        e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
      }
    : undefined;

  return (
    <Tag ref={ref} className={`rv ${spot ? "spot" : ""} ${className}`} style={{ "--rv-delay": `${delay}ms` } as React.CSSProperties} onPointerMove={onMove}>
      {children}
    </Tag>
  );
}

/** Thin progress bar at the top of the window that fills as you scroll. */
export function ScrollProgress() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      el.style.setProperty("--p", String(max > 0 ? h.scrollTop / max : 0));
      raf = 0;
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  return <div ref={ref} className="scroll-progress" aria-hidden />;
}

/** A big number that counts up the first time it scrolls into view. */
export function CountStat({ value, label }: { value: number; label: string }) {
  const num = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = num.current;
    if (!el || reducedMotion()) return;
    let raf = 0;
    el.textContent = "0";
    const io = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (now: number) => {
        const k = Math.min(1, (now - t0) / 1400);
        el.textContent = String(Math.round(value * (1 - Math.pow(1 - k, 3))));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, { threshold: 0.6 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [value]);

  return (
    <FX spot className="glass p-4">
      <dt className="sr-only">{label}</dt>
      <dd ref={num} className="text-4xl font-semibold tabular-nums">{value}</dd>
      <dd className="mt-0.5 text-sm text-muted">{label}</dd>
    </FX>
  );
}
