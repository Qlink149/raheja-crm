/**
 * Parse API datetimes as UTC (naive ISO strings are treated as UTC).
 */
export function parseUtc(dateStr) {
  if (!dateStr) return null;
  const s = String(dateStr).trim();
  if (!s) return null;
  if (s.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(s)) {
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const normalized = s.includes("T") ? `${s}Z` : `${s}T00:00:00Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Format UTC instant for India display (AI Calling, call history). */
export function formatDateTimeIST(dateStr, options = {}) {
  const d = parseUtc(dateStr);
  if (!d) return "N/A";
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...options,
  });
}

/** Short date for context timeline (IST). */
export function formatDateOnlyIST(dateStr) {
  const d = parseUtc(dateStr);
  if (!d) return "—";
  return d.toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}
