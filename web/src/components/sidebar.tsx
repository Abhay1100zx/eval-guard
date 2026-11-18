"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { UserButton } from "@clerk/nextjs";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: "📊" },
  { href: "/benchmark", label: "Domains", icon: "🌐" },
  { href: "/runs", label: "Runs", icon: "🔍" },
  { href: "/drift", label: "Drift", icon: "⚠️" },
  { href: "/playground", label: "Playground", icon: "🧪" },
  { href: "/evaluate", label: "Evaluate", icon: "🚀" },
  { href: "/experiments", label: "Experiments", icon: "⚗️" },
  { href: "/prompts", label: "Prompts", icon: "📝" },
  { href: "/questions", label: "Test cases", icon: "🧷" },
  { href: "/documents", label: "Documents", icon: "📁" },
];

const isActive = (path: string, href: string) => path === href || path.startsWith(href + "/");

// Collapsed state is remembered per browser. Storage can be blocked, so every access is guarded.
const KEY = "evalguard.sidebar.collapsed";
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
};
const getCollapsed = () => {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
};
const setCollapsed = (v: boolean) => {
  try { localStorage.setItem(KEY, v ? "1" : "0"); } catch {}
  listeners.forEach((l) => l());
};

export function Sidebar() {
  const path = usePathname();
  const collapsed = useSyncExternalStore(subscribe, getCollapsed, () => false);

  return (
    <>
      {/* Desktop: floating glass sidebar that collapses to an icon rail */}
      <aside
        data-collapsed={collapsed}
        className={`glass-strong sticky top-4 m-4 mr-0 hidden h-[calc(100vh-2rem)] shrink-0 flex-col overflow-hidden rounded-[1.75rem] p-3 transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] md:flex ${
          collapsed ? "w-[4.75rem]" : "w-60"
        }`}
      >
        <div className={`flex items-center pb-3 pt-2 ${collapsed ? "justify-center" : "justify-between pl-3"}`}>
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-lg font-semibold tracking-tight">🛡️ EvalGuard</div>
              <div className="truncate text-xs text-muted">RAG evaluation & drift</div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="btn-spring glass-inset grid size-9 shrink-0 place-items-center rounded-full text-muted hover:text-foreground"
          >
            <span aria-hidden className={`text-lg leading-none transition-transform duration-500 ${collapsed ? "rotate-180" : ""}`}>‹</span>
          </button>
        </div>

        <nav aria-label="Main" className="flex flex-1 flex-col gap-1">
          {NAV.map((n) => {
            const active = isActive(path, n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                title={collapsed ? n.label : undefined}
                aria-label={collapsed ? n.label : undefined}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-2xl py-2.5 text-sm font-medium transition-all duration-300 ${
                  collapsed ? "justify-center px-0" : "px-3.5"
                } ${active ? "glass-pill-active text-foreground" : "text-muted hover:bg-surface-2 hover:text-foreground"}`}
              >
                <span aria-hidden className={`text-base transition-transform duration-300 ${active ? "scale-110" : ""}`}>{n.icon}</span>
                {!collapsed && <span className="truncate">{n.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className={`glass-inset flex items-center rounded-2xl py-3 ${collapsed ? "justify-center" : "gap-3 px-3.5"}`}>
          <UserButton />
          {!collapsed && <span className="text-xs text-muted">Account</span>}
        </div>
      </aside>

      {/* Mobile: top bar + iOS-style floating tab bar */}
      <header className="glass-strong sticky top-3 z-30 mx-3 mt-3 flex items-center justify-between rounded-full px-5 py-2.5 md:hidden">
        <span className="font-semibold tracking-tight">🛡️ EvalGuard</span>
        <UserButton />
      </header>
      <nav aria-label="Main" className="glass-strong fixed inset-x-3 bottom-3 z-40 flex gap-0.5 overflow-x-auto rounded-full p-1.5 md:hidden">
        {NAV.map((n) => {
          const active = isActive(path, n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-w-[4.1rem] flex-1 flex-col items-center gap-0.5 rounded-full px-2 py-1.5 text-[10px] font-medium transition-all duration-300 ${
                active ? "glass-pill-active text-foreground" : "text-muted"
              }`}
            >
              <span aria-hidden className="text-base leading-none">{n.icon}</span>
              {n.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
