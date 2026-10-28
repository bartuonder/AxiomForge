import { formatNumber, type Tone } from "./format.ts";
import type { Language } from "./i18n.ts";
import type { Confirmation, ConfirmationStatus, RegisteredHypothesis } from "./types.ts";

export const STATUS_ORDER: ConfirmationStatus[] = ["confirmed", "reversed", "not_confirmed", "not_testable"];

export type SessionRow = { hypothesis: RegisteredHypothesis; confirmation: Confirmation | null };

const STATUS_TONES: Record<string, Tone> = { confirmed: "positive", reversed: "negative", not_confirmed: "neutral", not_testable: "muted" };
const SESSION_TONES: Record<string, Tone> = { completed: "positive", running: "neutral", aborted: "warning", failed: "negative" };

export function statusTone(status: string): Tone {
  return STATUS_TONES[status] ?? "muted";
}

export function sessionTone(status: string): Tone {
  return SESSION_TONES[status] ?? "muted";
}

function side(keys: string[], names: Record<string, string>): string {
  return keys.map((key) => names[key] ?? key).join(" + ");
}

export function claimText(subject: string[], other: string[], names: Record<string, string>): string {
  return `${side(subject, names)} ≻ ${side(other, names)}`;
}

export function formatP(value: number | null, language: Language): string {
  if (value === null) {
    return "–";
  }
  if (value < 0.001) {
    return language === "tr" ? "<0,001" : "<0.001";
  }
  return formatNumber(value, language, 3);
}

export function mergeRows(hypotheses: RegisteredHypothesis[], confirmations: Confirmation[] | undefined): SessionRow[] {
  const byId = new Map((confirmations ?? []).map((item) => [item.id, item]));
  return hypotheses.map((hypothesis) => ({ hypothesis, confirmation: byId.get(hypothesis.id) ?? null }));
}
