import { Term } from "@/components/Term";
import type { SummaryConfidence } from "@/lib/types";

const FILLED = { high: 3, medium: 2, low: 1 } as const;
const COLORS = { high: "bg-[#1f6b4a]", medium: "bg-[#c9a227]", low: "bg-[#a3988c]" } as const;

export function ConfidenceMeter({ confidence }: { confidence: SummaryConfidence }) {
  const filled = FILLED[confidence.level];
  return (
    <div className="flex items-start gap-3">
      <div className="mt-1.5 flex gap-1" aria-hidden="true">
        {[1, 2, 3].map((step) => (
          <span key={step} className={`h-2 w-6 rounded-full ${step <= filled ? COLORS[confidence.level] : "bg-[#e4ddd2]"}`} />
        ))}
      </div>
      <p className="text-sm text-[#5c564e]">
        <span className="font-semibold text-[#1c1915]">
          <Term id="confidence">{confidence.label}</Term>
        </span>
        <span className="block">{confidence.reason}</span>
      </p>
    </div>
  );
}
