"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

const LINKS = [
  { href: "#problem", label: "The problem" },
  { href: "#how", label: "How it works" },
  { href: "#tour", label: "Product tour" },
  { href: "#features", label: "Features" },
  { href: "#safety", label: "Safety" },
  { href: "#technology", label: "Technology" },
  { href: "#faq", label: "FAQ" },
];

/** Sign-in or dashboard button that follows the visitor's session. Shows "Sign in" until Clerk has loaded. */
export function AuthButton({ className = "" }: { className?: string }) {
  const { isLoaded, isSignedIn } = useAuth();
  const signedIn = isLoaded && isSignedIn;
  return (
    <Link
      href={signedIn ? "/dashboard" : "/sign-in"}
      className={`btn-primary btn-spring inline-flex items-center justify-center gap-2 rounded-full px-5 py-2 text-sm font-medium text-white ${className}`}
    >
      {signedIn ? "Open dashboard" : "Sign in"}
    </Link>
  );
}

export function LandingNav() {
  return (
    <header className="glass-strong sticky top-3 z-40 mx-auto mt-3 flex w-[calc(100%-1.5rem)] max-w-6xl items-center justify-between gap-4 rounded-full px-5 py-2.5">
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <span aria-hidden>🛡️</span> EvalGuard
      </Link>
      <nav aria-label="Page sections" className="hidden items-center gap-1 lg:flex">
        {LINKS.map((l) => (
          <a key={l.href} href={l.href} className="rounded-full px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-surface-2 hover:text-foreground">
            {l.label}
          </a>
        ))}
      </nav>
      <AuthButton />
    </header>
  );
}
