"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Polls an async fetcher on a fixed interval while the tab is visible.
 * Returns the latest data, error state, a manual refresh and loading flag.
 * External API calls are never triggered by these polls — the FastAPI
 * backend serves cached/database state; only its scheduler spends quota.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const tick = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    tick();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, intervalMs);
    return () => clearInterval(id);
  }, [tick, intervalMs]);

  return { data, error, loading, refresh: tick };
}
