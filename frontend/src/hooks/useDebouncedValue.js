import { useState, useEffect, useCallback } from "react";

/**
 * Debounces a value. Optionally enforces a minimum character length before
 * propagating non-empty search terms (empty always flushes immediately).
 */
export function useDebouncedValue(value, delay = 400, { minLength = 0 } = {}) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const trimmed = typeof value === "string" ? value.trim() : value;
    if (minLength > 0 && trimmed && String(trimmed).length < minLength) {
      const t = setTimeout(() => setDebounced(""), delay);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay, minLength]);

  const flush = useCallback(() => {
    const trimmed = typeof value === "string" ? value.trim() : value;
    if (minLength > 0 && trimmed && String(trimmed).length < minLength) {
      setDebounced("");
      return;
    }
    setDebounced(value);
  }, [value, minLength]);

  return [debounced, flush];
}
