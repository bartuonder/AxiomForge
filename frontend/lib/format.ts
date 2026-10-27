import type { Language } from "./i18n.ts";

export type Tone = "positive" | "negative" | "neutral" | "warning" | "muted";

export type TonePalette = { badge: string; soft: string; bar: string; text: string };

export const TONES: Record<Tone, TonePalette> = {
  positive: { badge: "border-[#b9d8c7] bg-[#eef6f1] text-[#14472f]", soft: "border-[#b9d8c7] bg-[#f4faf6]", bar: "bg-[#1f6b4a]", text: "text-[#14472f]" },
  negative: { badge: "border-[#d9a99e] bg-[#faeeea] text-[#6e2a1c]", soft: "border-[#e6c2b9] bg-[#fdf6f4]", bar: "bg-[#b4452f]", text: "text-[#6e2a1c]" },
  neutral: { badge: "border-[#c5cdd6] bg-[#eef1f5] text-[#2f3b4a]", soft: "border-[#d4dae1] bg-[#f6f8fa]", bar: "bg-[#5b6b7d]", text: "text-[#2f3b4a]" },
  warning: { badge: "border-[#e0c46a] bg-[#fbf3d6] text-[#5c4a0c]", soft: "border-[#ead9a0] bg-[#fdf9e8]", bar: "bg-[#c9a227]", text: "text-[#5c4a0c]" },
  muted: { badge: "border-[#d7d0c4] bg-white text-[#5c564e]", soft: "border-[#e4ddd2] bg-[#faf8f3]", bar: "bg-[#a3988c]", text: "text-[#5c564e]" },
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

export function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}
