import { BRAND } from "../lib/brandConfig";

/** Vendor display name shown in UI / transcripts */
export const WHITELABEL_AGENT_LABEL = BRAND.aiAgentLabel;

/**
 * Replace vendor agent branding in free text (transcripts, summaries).
 */
export function whitelabelAgentText(text) {
  if (text == null || text === "") return text;
  return String(text).replace(/\bFutwork\s+Agent\b/gi, WHITELABEL_AGENT_LABEL);
}

function normalizeNewlines(raw) {
  let s = String(raw ?? "");
  if (s.includes("\\n") && !s.includes("\n")) {
    s = s.replace(/\\n/g, "\n");
  }
  return s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

/**
 * Speaker label at line start (leading whitespace allowed).
 * English dialer labels + Hindi customer labels; body may be any Unicode.
 */
export const SPEAKER_LINE_RE =
  /^\s*(User|Customer|Assistant|AI\s*Agent|Futwork\s*Agent|Agent|System|Bot|ग्राहक|यूज़र|उपयोगकर्ता)\s*:\s*(.*)$/isu;

/** @typedef {'normal' | 'swapped' | 'unknown'} TranscriptSpeakerMode */

const AGENT_BODY_PATTERNS = [
  /मैं\s+प्रिया/i,
  /\bpriya\b/i,
  /राहेजा/i,
  /\braheja\b/i,
  /क्या\s+मैं\s+.+\s+से\s+बात\s+कर\s+रही\s+हूं/i,
  /देखिए\s+आपने\s+पहले\s+राहेजा/i,
  /राहेजा\s*डेवलपर्स/i,
];

export function normalizeSpeakerLabel(labelRaw) {
  const trimmed = String(labelRaw ?? "").trim();
  if (/[\u0900-\u097F]/.test(trimmed)) {
    return trimmed.replace(/\s+/g, "");
  }
  return trimmed.toLowerCase().replace(/\s+/g, "");
}

export function isCustomerSideLabel(norm) {
  return (
    norm === "user" ||
    norm === "customer" ||
    norm === "ग्राहक" ||
    norm === "यूज़र" ||
    norm === "उपयोगकर्ता"
  );
}

export function isAgentSideLabel(norm) {
  return (
    norm === "assistant" ||
    norm === "agent" ||
    norm === "bot" ||
    norm === "system" ||
    norm === "futworkagent" ||
    norm === "aiagent"
  );
}

/**
 * Outbound Voice AI speaks first; first labeled line identifies vendor label mapping.
 * @param {string[]} lines
 * @returns {TranscriptSpeakerMode}
 */
export function detectTranscriptSpeakerMode(lines) {
  for (const rawLine of lines) {
    const m = rawLine.match(SPEAKER_LINE_RE);
    if (!m) continue;
    const norm = normalizeSpeakerLabel(m[1] || "");
    if (isCustomerSideLabel(norm)) return "swapped";
    if (isAgentSideLabel(norm)) return "normal";
    return "normal";
  }
  return "normal";
}

/**
 * @param {string} norm
 * @param {TranscriptSpeakerMode} mode
 * @returns {boolean}
 */
export function labelToIsCustomer(norm, mode) {
  const customer = isCustomerSideLabel(norm);
  const agent = isAgentSideLabel(norm);
  if (mode === "swapped") {
    if (customer) return false;
    if (agent) return true;
    return false;
  }
  if (customer) return true;
  if (agent) return false;
  return false;
}

export function bodyIndicatesAgent(text) {
  const t = String(text ?? "").trim();
  if (!t) return false;
  return AGENT_BODY_PATTERNS.some((re) => re.test(t));
}

/**
 * Parse a call transcript into ordered turns; continuation lines merge into the current turn.
 * @returns {{ isUser: boolean, text: string }[]}
 */
export function parseCallTranscriptTurns(raw) {
  const text = whitelabelAgentText(normalizeNewlines(raw));
  const lines = text.split("\n");
  const mode = detectTranscriptSpeakerMode(lines);
  /** @type {{ isUser: boolean, body: string[] }[]} */
  const turns = [];
  let cur = null;

  for (const rawLine of lines) {
    const m = rawLine.match(SPEAKER_LINE_RE);
    if (m) {
      const norm = normalizeSpeakerLabel(m[1] || "");
      const body = (m[2] ?? "").replace(/\s+$/u, "");
      let isUser = labelToIsCustomer(norm, mode);
      cur = { isUser, body: [body] };
      turns.push(cur);
    } else if (cur) {
      cur.body.push(rawLine);
    } else if (rawLine.trim()) {
      cur = { isUser: false, body: [rawLine] };
      turns.push(cur);
    }
  }

  return turns
    .map((t) => {
      let isUser = t.isUser;
      const joined = t.body.join("\n").trim();
      if (bodyIndicatesAgent(joined)) {
        isUser = false;
      }
      return { isUser, text: joined };
    })
    .filter((t) => t.text);
}
