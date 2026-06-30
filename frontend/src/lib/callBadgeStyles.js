/** Theme-aware disposition & status badge class names (styles in index.css). */

export const DISPOSITION_BADGE_CLASS = {
  Interested: "call-badge call-badge--interested",
  "Partially Interested": "call-badge call-badge--partial",
  "Site Visit": "call-badge call-badge--site-visit",
  "Not Interested": "call-badge call-badge--not-interested",
  Busy: "call-badge call-badge--busy",
  Dropped: "call-badge call-badge--dropped",
  "Incomplete conversation": "call-badge call-badge--incomplete",
};

export const STATUS_BADGE_CLASS = {
  completed: "call-badge call-badge--status-completed",
  "no-answer": "call-badge call-badge--status-no-answer",
  busy: "call-badge call-badge--status-busy",
  failed: "call-badge call-badge--status-failed",
};

export const getDispositionBadgeClass = (disposition) =>
  DISPOSITION_BADGE_CLASS[disposition] || "call-badge call-badge--default";

export const getStatusBadgeClass = (status) =>
  STATUS_BADGE_CLASS[status] || "call-badge call-badge--default";

const DISPOSITION_ALIASES = {
  interested: "Interested",
  "not interested": "Not Interested",
  "partially interested": "Partially Interested",
  "site visit": "Site Visit",
  busy: "Busy",
  dropped: "Dropped",
  "incomplete conversation": "Incomplete conversation",
};

/** Resolve badge class from disposition and/or status (customer timeline, etc.) */
export const getCallTimelineBadgeClass = (disposition, status) => {
  const rawDisposition = (disposition || "").trim();
  const d = rawDisposition.toLowerCase();
  const s = (status || "").trim().toLowerCase();

  if (rawDisposition) {
    if (DISPOSITION_BADGE_CLASS[rawDisposition]) {
      return DISPOSITION_BADGE_CLASS[rawDisposition];
    }
    const aliasKey = DISPOSITION_ALIASES[d];
    if (aliasKey && DISPOSITION_BADGE_CLASS[aliasKey]) {
      return DISPOSITION_BADGE_CLASS[aliasKey];
    }
  }

  if (s && STATUS_BADGE_CLASS[s]) {
    return STATUS_BADGE_CLASS[s];
  }

  return "call-badge call-badge--default";
};
