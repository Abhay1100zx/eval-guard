import { Suspense } from "react";
import { Sidebar } from "@/components/sidebar";
import { PageTransition } from "@/components/page-transition";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Suspense fallback={null}>
        <Sidebar />
      </Suspense>
      <main className="min-w-0 flex-1 px-4 pb-28 pt-6 md:px-8 md:pb-10 md:pt-8">
        <div className="mx-auto max-w-6xl">
          <Suspense fallback={<div role="status" className="py-8 text-sm text-muted">Loading…</div>}>
            <PageTransition>{children}</PageTransition>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
