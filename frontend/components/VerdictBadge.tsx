import { tonePalette } from "@/lib/format";

const ICONS: Record<string, string> = { positive: "✓", negative: "✕", neutral: "≈", warning: "◑", muted: "?" };

type VerdictBadgeProps = {
  label: string;
  tone: string;
  large?: boolean;
};

export function VerdictBadge({ label, tone, large = false }: VerdictBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border font-semibold ${tonePalette(tone).badge} ${large ? "px-4 py-1.5 text-base" : "px-3 py-0.5 text-xs"}`}
    >
      <span aria-hidden="true">{ICONS[tone] ?? ICONS.muted}</span>
      {label}
    </span>
  );
}
