import { formatNumber, type Tone } from "./format.ts";
import type { Language } from "./i18n.ts";
import type { Confirmation, ConfirmationStatus, RegisteredHypothesis } from "./types.ts";

export const STATUS_ORDER: ConfirmationStatus[] = ["confirmed", "reversed", "not_confirmed", "not_testable"];

export type SessionRow = { hypothesis: RegisteredHypothesis; confirmation: Confirmation | null };

const STATUS_TONES: Record<string, Tone> = { confirmed: "positive", reversed: "negative", not_confirmed: "neutral", not_testable: "muted" };
const SESSION_TONES: Record<string, Tone> = { completed: "positive", queued: "neutral", running: "neutral", aborted: "warning", failed: "negative", cancelled: "muted" };

export const ACTIVE_SESSION_STATUSES = ["queued", "running"];
export const RETRYABLE_SESSION_STATUSES = ["failed", "cancelled", "aborted"];
export const RESEARCH_MODELS = [
  "RandomForest",
  "ExtraTrees",
  "GradientBoosting",
  "HistGradientBoosting",
  "XGBoost",
  "LightGBM",
  "CatBoost",
  "MLP",
  "LogisticRegression",
  "SVM",
  "KNN",
  "DecisionTree",
  "AdaBoost",
  "GaussianNB",
  "LDA",
  "QDA",
  "LinearSVC",
];
export const DEFAULT_RESEARCH_MODELS = ["RandomForest", "ExtraTrees", "GradientBoosting", "HistGradientBoosting", "MLP", "LogisticRegression"];
export const TUNING_ITERATIONS = 12;
export const MIN_RESEARCH_MODELS = 2;

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

export type StartChoices = { models: string[]; tuned: boolean; generator: "rules" | "llm" };

export type StartPayload = { models: string[]; generator: "rules" | "llm"; tuning?: number };

export function isActiveSession(status: string): boolean {
  return ACTIVE_SESSION_STATUSES.includes(status);
}

export function sessionActions(status: string, cancelRequested: boolean): { cancel: boolean; retry: boolean; cancelling: boolean } {
  const active = isActiveSession(status);
  return { cancel: active && !cancelRequested, cancelling: active && cancelRequested, retry: RETRYABLE_SESSION_STATUSES.includes(status) };
}

export function toggleModel(selected: string[], key: string): string[] {
  return selected.includes(key) ? selected.filter((item) => item !== key) : RESEARCH_MODELS.filter((item) => item === key || selected.includes(item));
}

export function canStart(choices: StartChoices): boolean {
  return choices.models.length >= MIN_RESEARCH_MODELS;
}

export function startPayload(choices: StartChoices): StartPayload {
  const base = { models: RESEARCH_MODELS.filter((key) => choices.models.includes(key)), generator: choices.generator };
  return choices.tuned ? { ...base, tuning: TUNING_ITERATIONS } : base;
}

export function phaseMessage(status: string, phase: string | undefined): string | null {
  if (status === "queued") {
    return "research.phase.queued";
  }
  if (status !== "running") {
    return null;
  }
  return phase === "default" || phase === "tuned" ? `research.phase.${phase}` : "research.phase.working";
}
