"use client";

import { usePathname } from "next/navigation";
import { ReactNode } from "react";

/** Re-runs a short fade/rise whenever the route changes. */
export function PageTransition({ children }: { children: ReactNode }) {
  const path = usePathname();
  return <div key={path} className="page-in">{children}</div>;
}
