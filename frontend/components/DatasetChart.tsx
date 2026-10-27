"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { barPercent, chartRange, formatNumber, winner } from "@/lib/format";
import type { SummaryChart } from "@/lib/types";

export function DatasetChart({ chart }: { chart: SummaryChart }) {
  const { language, t } = useLanguage();
  const range = chartRange(chart.points);
  return (
    <figure className="space-y-3">
      <figcaption className="text-sm font-semibold text-ink">{t("claim.chartTitle", { metric: chart.metric_label })}</figcaption>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-accent" aria-hidden="true" />
          {chart.subject_label}
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-dim" aria-hidden="true" />
          {chart.other_label}
        </span>
      </div>
      <ul className="space-y-3">
        {chart.points.map((point) => {
          const ahead = winner(point);
          return (
            <li key={point.dataset} className="grid gap-1 sm:grid-cols-[minmax(0,13rem)_1fr] sm:items-center sm:gap-4">
              <span className="text-sm text-ink">{point.label}</span>
              <div className="space-y-1">
                {(["subject", "other"] as const).map((side) => (
                  <div key={side} className="flex items-center gap-2">
                    <div className="h-3 flex-1 rounded-full bg-track">
                      <div
                        className={`h-3 rounded-full ${side === "subject" ? "bg-accent" : "bg-dim"}`}
                        style={{ width: `${barPercent(point[side], range)}%` }}
                      />
                    </div>
                    <span className={`w-12 text-right text-xs tabular-nums ${ahead === side ? "font-semibold text-ink" : "text-muted"}`}>
                      {formatNumber(point[side], language, 3)}
                    </span>
                  </div>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-faint">{t("claim.chartNote", { start: formatNumber(range.start, language, 1) })}</p>
    </figure>
  );
}
