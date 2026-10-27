"use client";

import { ClaimCard } from "@/components/ClaimCard";
import { useLanguage } from "@/components/LanguageProvider";
import { Term } from "@/components/Term";
import type { PlainSummary } from "@/lib/types";

const COMPACT_FROM = 3;

export function SummaryView({ summary }: { summary: PlainSummary }) {
  const { t } = useLanguage();
  if (summary.claims.length === 0) {
    return (
      <section className="space-y-4">
        <p className="text-[#5c564e]">{t("campaign.waiting")}</p>
        <div className="h-3 overflow-hidden rounded-full bg-[#ece6da]" aria-hidden="true">
          <div className="h-3 rounded-full bg-[#1f6b4a] transition-all" style={{ width: `${summary.progress.percent}%` }} />
        </div>
        <p className="text-sm text-[#5c564e]">{t("campaign.progress", { finished: summary.progress.finished, total: summary.progress.total })}</p>
      </section>
    );
  }
  return (
    <div className="space-y-10">
      {summary.claims.length > 1 ? <p className="text-lg text-[#1c1915]">{summary.headline}</p> : null}
      <div className="space-y-8">
        {summary.claims.map((claim, index) => (
          <ClaimCard key={claim.id} claim={claim} compact={summary.claims.length > COMPACT_FROM} open={index === 0} />
        ))}
      </div>

      <section className="grid gap-8 sm:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-xl text-[#1c1915]">{t("campaign.howTitle")}</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-[#5c564e]">
            {summary.method.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3">
          <h2 className="text-xl text-[#1c1915]">{t("campaign.cautionTitle")}</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-[#5c4a0c]">
            {summary.cautions.map((caution) => (
              <li key={caution}>{caution}</li>
            ))}
          </ul>
        </div>
      </section>

      {summary.ranking.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl text-[#1c1915]">{t("campaign.rankingTitle")}</h2>
          <p className="text-sm text-[#5c564e]">{t("campaign.rankingHint")}</p>
          <ol className="space-y-2">
            {summary.ranking.map((item) => (
              <li key={item.model} className="flex items-center gap-3 rounded-xl border border-[#e4ddd2] bg-white px-4 py-2 text-sm">
                <span className="w-6 font-semibold text-[#1f6b4a]">{item.position}</span>
                <span className="flex-1 text-[#1c1915]">{item.label}</span>
                <span className="text-xs text-[#8a8175] tabular-nums">{item.average_rank.toFixed(1)}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xl text-[#1c1915]">
          <Term id="dataset">{t("campaign.datasetsTitle")}</Term>
        </h2>
        <ul className="flex flex-wrap gap-2">
          {summary.datasets.map((item) => (
            <li key={item.key} className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs text-[#5c564e]">
              {item.label}
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl text-[#1c1915]">{t("campaign.glossaryTitle")}</h2>
        <dl className="grid gap-3 sm:grid-cols-2">
          {Object.entries(summary.glossary).map(([key, entry]) => (
            <div key={key} className="rounded-xl border border-[#e4ddd2] bg-white p-3">
              <dt className="text-sm font-semibold text-[#1f6b4a]">{entry.term}</dt>
              <dd className="mt-1 text-xs leading-5 text-[#5c564e]">{entry.explanation}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
