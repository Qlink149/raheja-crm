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

const IST_TIMEZONE = "Asia/Kolkata";

/** Calendar date in local picker coordinates (avoids UTC shift from toISOString). */
export function toCalendarDateString(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Build start_date/end_date query params for call-history APIs (IST calendar days). */
export function buildCallHistoryDateParams(dateRange) {
  if (!dateRange?.from) return {};
  return {
    start_date: toCalendarDateString(dateRange.from),
    end_date: toCalendarDateString(dateRange.to || dateRange.from),
  };
}

/** Label for AI Calling date filter button. */
export function formatCallHistoryDateLabel(dateRange) {
  if (!dateRange?.from) return "Filter by date";
  const opts = { day: "numeric", month: "short", year: "numeric", timeZone: IST_TIMEZONE };
  const fromLabel = dateRange.from.toLocaleDateString("en-IN", opts);
  const to = dateRange.to || dateRange.from;
  const toLabel = to.toLocaleDateString("en-IN", opts);
  if (fromLabel === toLabel) return fromLabel;
  return `${fromLabel} – ${toLabel}`;
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
