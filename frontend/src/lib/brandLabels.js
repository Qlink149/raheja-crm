/** User-visible labels — internal API keys may still use futwork_*. */

import { BRAND } from "./brandConfig";

export const CALLING_ENGINE_NAME = "Calling Engine";

const SOURCE_LABELS = {
  "Futwork CSV Import": "Platform Pipeline",
  futwork_orphan_call: "Inbound Call",
  futwork: "Calling Engine",
};

export function mapLeadSourceLabel(raw) {
  const s = String(raw || "").trim();
  if (!s) return "Direct";
  if (SOURCE_LABELS[s]) return SOURCE_LABELS[s];
  if (/futwork/i.test(s)) return "Calling Engine";
  return s;
}

/** Replace vendor name in API error messages shown in toasts. */
export function sanitizeApiErrorMessage(message) {
  if (message == null || message === "") return message;
  return String(message).replace(/\bFutwork\b/gi, CALLING_ENGINE_NAME);
}

/** White-label notification title/message text (bell + notifications page). */
export function sanitizeNotificationText(text) {
  if (text == null || text === "") return text ?? "";
  let s = String(text);
  s = s.replace(/\bFutwork\s+Agent\b/gi, BRAND.aiAgentLabel);
  for (const [key, label] of Object.entries(SOURCE_LABELS)) {
    s = s.replace(new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), label);
  }
  s = s.replace(/\bfutwork_orphan_call\b/gi, "Inbound Call");
  s = s.replace(/\bFutwork\b/gi, CALLING_ENGINE_NAME);
  return s;
}

export const isNotificationUnread = (n) => n?.is_read !== true;

export const UI_COPY = {
  engineCalled: "Engine Called",
  pushToCallingEngine: "Push to Calling Engine",
  pushDbToCallingEngine: "Push DB leads to Calling Engine",
  callingEngineNotConfigured: `${CALLING_ENGINE_NAME} is not configured on the server.`,
  callingEngineDialOut: `${CALLING_ENGINE_NAME} dial-out`,
  bulkPushBatchNote: `This batch was created from a DB bulk ${CALLING_ENGINE_NAME} push (no CSV file).`,
  eligiblePushHint:
    "leads in the database can still be pushed to Calling Engine (pending or failed sync, valid phone + Lead ID).",
};
