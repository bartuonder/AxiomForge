"use client";

import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { DatasetChart } from "@/components/DatasetChart";
import { useLanguage } from "@/components/LanguageProvider";
import { Term } from "@/components/Term";
import { VerdictBadge } from "@/components/VerdictBadge";
import { formatSigned, ratio, tonePalette } from "@/lib/format";
import type { SummaryClaim } from "@/lib/types";

const GLOSSARY_FOR_METRIC: Record<string, string> = { roc_auc: "roc_auc", pr_auc: "pr_auc", f1: "f1" };

type ClaimCardProps = {
  claim: SummaryClaim;
  compact?: boolean;
  open?: boolean;
};

function ClaimBody({ claim }: { claim: SummaryClaim }) {
  const { language, t } = useLanguage();
  const refuted = claim.verdict.code === "contradicted";
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">{claim.verdict.meaning}</p>
      <p className="text-sm text-muted">
        <span className="font-semibold">{t("claim.statement")}:</span> {claim.statement}
      </p>

      <div className="grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
        <div className="rounded-2xl bg-card/70 px-6 py-4 text-center">
          <p className="font-[family-name:var(--font-display)] text-4xl font-semibold text-ink">{ratio(claim.datasets_for, claim.datasets_total)}</p>
          <p className="mt-1 max-w-[12rem] text-xs text-muted">
            <Term id="dataset">{refuted ? t("claim.datasetsForRefuted") : t("claim.datasetsFor")}</Term>
          </p>
        </div>
        <ConfidenceMeter confidence={claim.confidence} />
      </div>

      <DatasetChart chart={claim.chart} />

      <details className="rounded-2xl bg-card/70 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-ink">{t("campaign.details")}</summary>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-faint">
                <th className="py-2 pr-4">{t("claim.measures")}</th>
                <th className="py-2 pr-4">{t("claim.datasetsFor")}</th>
                <th className="py-2 pr-4">{t("claim.medianDifference")}</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {claim.metrics.map((row) => (
                <tr key={row.metric} className="border-b border-line-soft align-top">
                  <td className="py-2 pr-4">
                    <Term id={GLOSSARY_FOR_METRIC[row.metric] ?? row.metric}>{row.label}</Term>
                    <span className="block text-xs text-faint">{row.meaning}</span>
                  </td>
                  <td className="py-2 pr-4 tabular-nums">{t("claim.measureWins", { wins: row.wins, total: row.total })}</td>
                  <td className="py-2 pr-4 tabular-nums">{formatSigned(row.median_difference, language, 4)}</td>
                  <td className="py-2 text-xs text-muted">{!row.testable ? t("claim.notTestable") : row.significant ? t("claim.significant") : t("claim.notSignificant")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function ClaimCard({ claim, compact = false, open = false }: ClaimCardProps) {
  const palette = tonePalette(claim.verdict.tone);
  if (compact) {
    return (
      <details open={open} className={`group rounded-3xl border ${palette.soft}`}>
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-5">
          <VerdictBadge label={claim.verdict.label} tone={claim.verdict.tone} />
          <span className="text-xs font-semibold tracking-[0.14em] text-faint uppercase">{claim.id}</span>
          <span className={`min-w-0 flex-1 text-lg leading-snug ${palette.text}`}>{claim.headline}</span>
          <span className="text-sm tabular-nums text-muted">{ratio(claim.datasets_for, claim.datasets_total)}</span>
        </summary>
        <div className="px-6 pb-6">
          <ClaimBody claim={claim} />
        </div>
      </details>
    );
  }
  return (
    <article className={`space-y-6 rounded-3xl border p-6 sm:p-8 ${palette.soft}`}>
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <VerdictBadge label={claim.verdict.label} tone={claim.verdict.tone} large />
          <span className="text-xs font-semibold tracking-[0.14em] text-faint uppercase">
            <Term id="verdict">{claim.id}</Term>
          </span>
        </div>
        <h2 className={`text-2xl leading-snug sm:text-3xl ${palette.text}`}>{claim.headline}</h2>
      </header>
      <ClaimBody claim={claim} />
    </article>
  );
}
