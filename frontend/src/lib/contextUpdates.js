import { parseUtc } from "./dateUtils";

const SKIP = new Set(["", "n/a", "unknown", "0", "profiling in progress"]);

function tsMs(value) {
  const d = parseUtc(value);
  return d ? d.getTime() : null;
}

function displayDate(value) {
  const d = parseUtc(value);
  if (!d) return "—";
  return d.toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function durationLabel(seconds) {
  const n = Math.floor(Number(seconds) || 0);
  if (n <= 0) return "";
  const mins = Math.floor(n / 60);
  const secs = n % 60;
  if (mins > 0) return ` (${mins}m ${secs}s)`;
  return ` (${secs}s)`;
}

function hasValue(value) {
  if (value == null) return false;
  const s = String(value).trim();
  return Boolean(s) && !SKIP.has(s.toLowerCase());
}

function entry({ at, icon, type, context, sortMs }) {
  const ms = sortMs != null ? sortMs : tsMs(at);
  return {
    at: at || "",
    date: displayDate(at),
    icon,
    type,
    context,
    sort_ms: ms || 0,
  };
}

/** Client fallback when API has not backfilled context_updates yet. */
export function buildContextUpdatesFromLeadAndCalls(lead, calls = []) {
  const entries = [];
  const rows = [...(calls || [])].sort(
    (a, b) =>
      (tsMs(b.created_at || b.call_date) || 0) - (tsMs(a.created_at || a.call_date) || 0)
  );

  let earliestMs = null;
  for (const call of rows) {
    const rawTs = call.created_at || call.call_date;
    const ms = tsMs(rawTs);
    if (ms != null && (earliestMs == null || ms < earliestMs)) earliestMs = ms;

    const label = (call.disposition || call.status || "completed").trim();
    entries.push(
      entry({
        at: rawTs,
        icon: "phone",
        type: "call",
        context: `Outbound call — ${label}${durationLabel(call.duration)}`,
        sortMs: ms,
      })
    );
  }

  if (hasValue(lead?.budget)) {
    entries.push(
      entry({
        at: lead.updated_at || lead.last_call_date,
        icon: "whatsapp",
        type: "whatsapp",
        context: `Budget: ${lead.budget}`,
      })
    );
  }

  if (hasValue(lead?.configuration)) {
    entries.push(
      entry({
        at: lead.updated_at || lead.last_call_date,
        icon: "phone",
        type: "call",
        context: `Interested in ${lead.configuration} configuration`,
      })
    );
  }

  if (hasValue(lead?.project)) {
    entries.push(
      entry({
        at: lead.updated_at || lead.last_call_date,
        icon: "human",
        type: "human",
        context: `Showed interest in ${lead.project}`,
      })
    );
  }

  if (earliestMs != null) {
    entries.push(
      entry({
        at: new Date(earliestMs).toISOString(),
        icon: "phone",
        type: "call",
        context: "Initial contact made",
        sortMs: earliestMs,
      })
    );
  }

  if (!entries.length) {
    return [entry({ at: null, icon: "phone", type: "call", context: "Initial contact made", sortMs: 0 })];
  }

  entries.sort((a, b) => (b.sort_ms || 0) - (a.sort_ms || 0));
  const seen = new Set();
  return entries
    .filter((e) => {
      const key = `${e.context}|${e.sort_ms}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map(({ sort_ms, ...rest }) => rest);
}
