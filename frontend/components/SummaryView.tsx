"use client";

import { ClaimCard } from "@/components/ClaimCard";
import { useLanguage } from "@/components/LanguageProvider";
import { LiveProgress } from "@/components/LiveProgress";
import { Term } from "@/components/Term";
import type { PlainSummary } from "@/lib/types";

const COMPACT_FROM = 3;

export function SummaryView({ summary }: { summary: PlainSummary }) {
  const { t } = useLanguage();
  if (summary.claims.length === 0) {
    const code = summary.status.code;
    if (code === "cancelled" || code === "failed") {
      return <p className="text-muted">{code === "cancelled" ? t("campaign.stoppedNote") : t("campaign.failedNote")}</p>;
    }
    return (
      <section>
        <LiveProgress summary={summary} />
      </section>
    );
  }
  return (
    <div className="space-y-10">
      {summary.claims.length > 1 ? <p className="text-lg text-ink">{summary.headline}</p> : null}
      <div className="space-y-8">
        {summary.claims.map((claim, index) => (
          <ClaimCard key={claim.id} claim={claim} compact={summary.claims.length > COMPACT_FROM} open={index === 0} />
        ))}
      </div>

      <section className="grid gap-8 sm:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-xl text-ink">{t("campaign.howTitle")}</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-muted">
            {summary.method.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3">
          <h2 className="text-xl text-ink">{t("campaign.cautionTitle")}</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-warn-ink">
            {summary.cautions.map((caution) => (
              <li key={caution}>{caution}</li>
            ))}
          </ul>
        </div>
      </section>

      {summary.ranking.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl text-ink">{t("campaign.rankingTitle")}</h2>
          <p className="text-sm text-muted">{t("campaign.rankingHint")}</p>
          <ol className="space-y-2">
            {summary.ranking.map((item) => (
              <li key={item.model} className="flex items-center gap-3 rounded-xl border border-line-soft bg-card px-4 py-2 text-sm">
                <span className="w-6 font-semibold text-accent">{item.position}</span>
                <span className="flex-1 text-ink">{item.label}</span>
                <span className="text-xs text-faint tabular-nums">{item.average_rank.toFixed(1)}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xl text-ink">
          <Term id="dataset">{t("campaign.datasetsTitle")}</Term>
        </h2>
        <ul className="flex flex-wrap gap-2">
          {summary.datasets.map((item) => (
            <li key={item.key} className="rounded-full border border-line bg-card px-3 py-1 text-xs text-muted">
              {item.label}
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl text-ink">{t("campaign.glossaryTitle")}</h2>
        <dl className="grid gap-3 sm:grid-cols-2">
          {Object.entries(summary.glossary).map(([key, entry]) => (
            <div key={key} className="rounded-xl border border-line-soft bg-card p-3">
              <dt className="text-sm font-semibold text-accent">{entry.term}</dt>
              <dd className="mt-1 text-xs leading-5 text-muted">{entry.explanation}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
