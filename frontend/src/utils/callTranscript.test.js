import {
  parseCallTranscriptTurns,
  detectTranscriptSpeakerMode,
  labelToIsCustomer,
  bodyIndicatesAgent,
} from "./callTranscript";

const NORMAL_TRANSCRIPT = `Assistant: नमस्ते। मैं प्रिया बात कर रही हूं रुस्तम जी डेवलपर्स से।
Assistant: क्या मैं ताजुद्दीन पिंस की से बात कर रही हूं?
User: बोलिए।
Assistant: देखिए आपने पहले रुस्तम जी की प्रॉपर्टी के बारे में जानकारी मांगी थी।
User: ढूंढ रही हूं।`;

const SWAPPED_TRANSCRIPT = `User: नमस्ते मैं प्रिया बात कर रही हूं रुस्तम जी डेवलपर्स से।
Assistant: हां बोलिए।
User: क्या मैं प्रति शर्मा जी से बात कर रही हूं?
Assistant: जी हां।`;

const MIXED_MISLABEL = `User: नमस्ते मैं प्रिया बात कर रही हूं रुस्तम जी डेवलपर्स से।
User: क्या मैं प्रति शर्मा जी से बात कर रही हूं?
Assistant: हां जी बोलिए।`;

const HINDI_CUSTOMER_LABEL = `Assistant: नमस्ते
ग्राहक: हां जी`;

describe("detectTranscriptSpeakerMode", () => {
  it("returns normal when Assistant speaks first", () => {
    expect(detectTranscriptSpeakerMode(NORMAL_TRANSCRIPT.split("\n"))).toBe("normal");
  });

  it("returns swapped when User speaks first with agent intro", () => {
    expect(detectTranscriptSpeakerMode(SWAPPED_TRANSCRIPT.split("\n"))).toBe("swapped");
  });
});

describe("labelToIsCustomer", () => {
  it("maps user to customer in normal mode", () => {
    expect(labelToIsCustomer("user", "normal")).toBe(true);
    expect(labelToIsCustomer("assistant", "normal")).toBe(false);
  });

  it("inverts mapping in swapped mode", () => {
    expect(labelToIsCustomer("user", "swapped")).toBe(false);
    expect(labelToIsCustomer("assistant", "swapped")).toBe(true);
  });
});

describe("bodyIndicatesAgent", () => {
  it("detects Priya intro phrases", () => {
    expect(bodyIndicatesAgent("नमस्ते मैं प्रिया बात कर रही हूं")).toBe(true);
    expect(bodyIndicatesAgent("हां जी बोलिए")).toBe(false);
  });
});

describe("parseCallTranscriptTurns", () => {
  it("normal call: agent left, customer right", () => {
    const turns = parseCallTranscriptTurns(NORMAL_TRANSCRIPT);
    expect(turns.length).toBeGreaterThanOrEqual(4);
    expect(turns[0].isUser).toBe(false);
    expect(turns[0].text).toMatch(/प्रिया/);
    const customerTurn = turns.find((t) => t.text.includes("बोलिए"));
    expect(customerTurn?.isUser).toBe(true);
  });

  it("swapped call: Priya intro is agent (left), not customer", () => {
    const turns = parseCallTranscriptTurns(SWAPPED_TRANSCRIPT);
    expect(turns[0].isUser).toBe(false);
    expect(turns[0].text).toMatch(/प्रिया/);
    expect(turns[1].isUser).toBe(true);
  });

  it("mixed mislabel: agent phrase on User line maps to agent", () => {
    const turns = parseCallTranscriptTurns(MIXED_MISLABEL);
    const priyaTurns = turns.filter((t) => t.text.includes("प्रिया") || t.text.includes("प्रति शर्मा"));
    expect(priyaTurns.every((t) => !t.isUser)).toBe(true);
  });

  it("Hindi customer label in normal mode", () => {
    const turns = parseCallTranscriptTurns(HINDI_CUSTOMER_LABEL);
    expect(turns[0].isUser).toBe(false);
    expect(turns[1].isUser).toBe(true);
    expect(turns[1].text).toMatch(/हां जी/);
  });

  it("handles escaped newlines", () => {
    const escaped = NORMAL_TRANSCRIPT.replace(/\n/g, "\\n");
    const turns = parseCallTranscriptTurns(escaped);
    expect(turns[0].isUser).toBe(false);
    expect(turns.length).toBeGreaterThan(1);
  });
});
