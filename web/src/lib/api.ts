"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Returns a fetch helper that attaches the Clerk session token. */
export function useApi() {
  const { getToken } = useAuth();
  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
      let res: Response;
      try {
        res = await fetch(`${API_URL}${path}`, { ...init, headers });
      } catch {
        throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
        } catch {}
        throw new ApiError(res.status, detail);
      }
      return res.json() as Promise<T>;
    },
    [getToken],
  );
}

/** GET a path (null = skip). Re-fetches when the path changes; `reload()` forces a refetch. */
export function useFetch<T>(path: string | null) {
  const api = useApi();
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<{ path: string | null; tick: number; data: T | null; error: string | null }>({
    path: null, tick: -1, data: null, error: null,
  });

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    api<T>(path)
      .then((data) => !cancelled && setState({ path, tick, data, error: null }))
      .catch((e) => !cancelled && setState({ path, tick, data: null, error: e instanceof Error ? e.message : String(e) }));
    return () => { cancelled = true; };
  }, [api, path, tick]);

  // derived, so there is no setState in the effect body and no stale data from a previous path
  const fresh = state.path === path;
  const loading = path !== null && !(fresh && state.tick === tick);
  return {
    data: fresh ? state.data : null,
    error: fresh && state.tick === tick ? state.error : null,
    loading,
    reload: () => setTick((t) => t + 1),
  };
}
