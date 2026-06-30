/** Theme-aware lead qualification, budget, and sync badge class names (styles in index.css). */

export const QUALIFICATION_BADGE_CLASS = {
  Hot: "lead-badge lead-badge--hot",
  Warm: "lead-badge lead-badge--warm",
  Cold: "lead-badge lead-badge--cold",
  Qualified: "lead-badge lead-badge--qualified",
  Dormant: "lead-badge lead-badge--dormant",
  "VIP Pipeline": "lead-badge lead-badge--vip",
};

export const getQualificationBadgeClass = (qualification) => {
  const v = (qualification || "").trim();
  return QUALIFICATION_BADGE_CLASS[v] || "lead-badge lead-badge--default";
};

/** Qualification filter chips in the sidebar */
export const getQualificationFilterClass = (option, isActive) => {
  if (!isActive) return "lead-badge lead-badge--filter-inactive";
  if (option === "all") return "lead-badge lead-badge--filter-all";
  return getQualificationBadgeClass(option);
};

export const getBudgetBadgeClass = (isHni) =>
  isHni ? "lead-badge lead-badge--hni" : "lead-badge lead-badge--budget";

export const SYNC_PENDING_BADGE_CLASS = "lead-badge lead-badge--sync-pending";
