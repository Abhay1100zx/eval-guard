export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <div className="text-2xl font-semibold tracking-tight">🛡️ EvalGuard AI</div>
        <p className="mt-1 text-sm text-muted">Sign in to evaluate and monitor your RAG systems</p>
      </div>
      {children}
    </main>
  );
}
