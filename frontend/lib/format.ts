import type { Language } from "./i18n.ts";

export type Tone = "positive" | "negative" | "neutral" | "warning" | "muted";

export type TonePalette = { badge: string; soft: string; bar: string; text: string };

export const TONES: Record<Tone, TonePalette> = {
  positive: { badge: "border-accent-line bg-accent-tint text-accent-ink", soft: "border-accent-line bg-good-soft", bar: "bg-accent", text: "text-accent-ink" },
  negative: { badge: "border-danger-line bg-danger-tint text-danger-ink", soft: "border-bad-soft-line bg-bad-soft", bar: "bg-bad-bar", text: "text-danger-ink" },
  neutral: { badge: "border-calm-line bg-calm-tint text-calm-ink", soft: "border-calm-soft-line bg-calm-soft", bar: "bg-calm-bar", text: "text-calm-ink" },
  warning: { badge: "border-warn-line bg-warn-tint text-warn-ink", soft: "border-warn-soft-line bg-warn-soft", bar: "bg-warn", text: "text-warn-ink" },
  muted: { badge: "border-line bg-card text-muted", soft: "border-line-soft bg-panel", bar: "bg-dim", text: "text-muted" },
};

export function tonePalette(tone: string): TonePalette {
  return TONES[tone as Tone] ?? TONES.muted;
}

const LOCALES: Record<Language, string> = { tr: "tr-TR", en: "en-US" };

export function formatNumber(value: number, language: Language, digits = 2): string {
  return new Intl.NumberFormat(LOCALES[language], { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

export function formatSigned(value: number, language: Language, digits = 3): string {
  const text = formatNumber(Math.abs(value), language, digits);
  if (value > 0) {
    return `+${text}`;
  }
  return value < 0 ? `−${text}` : text;
}

export function ratio(count: number, total: number): string {
  return `${count} / ${total}`;
}

export type ChartPoint = { dataset: string; label: string; subject: number; other: number };

export type ChartRange = { start: number; end: number };

export function chartRange(points: ChartPoint[]): ChartRange {
  const scores = points.flatMap((point) => [point.subject, point.other]);
  if (scores.length === 0) {
    return { start: 0, end: 1 };
  }
  const lowest = Math.min(...scores);
  const start = Math.max(0, Math.floor((lowest - 0.05) * 10) / 10);
  return { start, end: 1 };
}

export function barPercent(value: number, range: ChartRange): number {
  const span = range.end - range.start;
  if (span <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, ((value - range.start) / span) * 100));
}

export function winner(point: ChartPoint): "subject" | "other" | "tie" {
  if (point.subject > point.other) {
    return "subject";
  }
  return point.subject < point.other ? "other" : "tie";
}

export function etaMinutes(seconds: number): number {
  return seconds < 60 ? 0 : Math.round(seconds / 60);
}

export function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}
