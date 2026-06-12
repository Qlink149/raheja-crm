import { useState, useEffect, useCallback, useRef } from "react";

/**
 * Lightweight fetch-state hook with initial-load vs refetch semantics.
 *
 * @param {() => Promise<any>} fetcher
 * @param {any[]} deps - refetch when these change
 * @param {{ enabled?: boolean, keepPreviousOnError?: boolean }} options
 */
export function useAsyncData(fetcher, deps = [], options = {}) {
  const { enabled = true, keepPreviousOnError = true } = options;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const hasLoadedOnce = useRef(false);

  const isInitialLoading = loading && !hasLoadedOnce.current;
  const isRefetching = loading && hasLoadedOnce.current;

  const run = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
      hasLoadedOnce.current = true;
    } catch (err) {
      setError(err);
      if (!keepPreviousOnError || !hasLoadedOnce.current) {
        setData(null);
      }
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetcher, enabled, keepPreviousOnError]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetcher();
        if (!cancelled) {
          setData(result);
          hasLoadedOnce.current = true;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err);
          if (!keepPreviousOnError || !hasLoadedOnce.current) {
            setData(null);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, keepPreviousOnError, ...deps]);

  const refetch = useCallback(() => run().catch(() => {}), [run]);

  return {
    data,
    error,
    loading,
    isInitialLoading,
    isRefetching,
    hasLoadedOnce: hasLoadedOnce.current,
    refetch,
    setData,
  };
}

/**
 * Format a stat value for display — never returns misleading 0 during load.
 */
export function formatStatValue(value, { loading = false, error = false, hasData = true } = {}) {
  if (loading && !hasData) return null;
  if (error && !hasData) return "—";
  if (value == null) return "—";
  return value;
}
