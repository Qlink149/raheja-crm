/** Format lead budget for Data DNA (prefers numeric crore over category band). */
export function formatLeadBudgetDisplay(lead) {
  if (!lead) return "";

  const se = lead.structured_extraction;
  const stated =
    (typeof se === "object" && se?.stated_budget_cr) || lead.stated_budget_cr || "";

  const candidates = [stated, lead.budget].filter(Boolean);
  for (const raw of candidates) {
    const s = String(raw).trim();
    if (!s || s === "0" || s.toLowerCase() === "profiling in progress") continue;
    if (/cr/i.test(s)) return s;
    return `${s} Cr`;
  }

  const bc = (lead.budget_category || "").trim();
  if (bc && bc !== "Other" && bc !== "Profiling in Progress") return bc;
  return "";
}

const NOT_WORTHY = "No meaningful conversation";

export function isUsableCallSummary(text) {
  const s = (text || "").trim();
  return Boolean(s) && s !== NOT_WORTHY;
}

export function canExpandCallSummary(call) {
  if (!call) return false;
  if (isUsableCallSummary(call.ai_call_summary)) return true;
  return call.ai_worthy !== false;
}

export function callSummaryDisabledReason(call) {
  if (canExpandCallSummary(call)) return undefined;
  if (call.ai_call_summary?.trim() === NOT_WORTHY) {
    return "This call was marked as having no meaningful conversation.";
  }
  return "AI summary unavailable — transcript format was not recognized for this call.";
}
