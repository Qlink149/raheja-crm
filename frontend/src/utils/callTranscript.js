/** Vendor display name shown in UI / transcripts */
export const WHITELABEL_AGENT_LABEL = "Rustomjee AI Sales Agent";

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
const SPEAKER_LINE_RE =
  /^\s*(User|Customer|Assistant|AI\s*Agent|Futwork\s*Agent|Agent|System|Bot|ग्राहक|यूज़र|उपयोगकर्ता)\s*:\s*(.*)$/su;

/**
 * Parse a call transcript into ordered turns; continuation lines merge into the current turn.
 * @returns {{ isUser: boolean, text: string }[]}
 */
export function parseCallTranscriptTurns(raw) {
  const text = whitelabelAgentText(normalizeNewlines(raw));
  const lines = text.split("\n");
  /** @type {{ isUser: boolean, body: string[] }[]} */
  const turns = [];
  let cur = null;

  const isUserLabel = (norm) =>
    norm === "user" ||
    norm === "customer" ||
    norm === "ग्राहक" ||
    norm === "यूज़र" ||
    norm === "उपयोगकर्ता";

  for (const rawLine of lines) {
    const m = rawLine.match(SPEAKER_LINE_RE);
    if (m) {
      const labelRaw = m[1] || "";
      const norm = labelRaw.toLowerCase().replace(/\s+/g, "");
      const body = (m[2] ?? "").replace(/\s+$/u, "");
      const isUser = isUserLabel(norm);
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
    .map((t) => ({
      isUser: t.isUser,
      text: t.body.join("\n").trim(),
    }))
    .filter((t) => t.text);
}
