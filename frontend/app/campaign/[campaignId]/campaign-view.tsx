"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CampaignBadge } from "@/components/CampaignBadge";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LedgerTable } from "@/components/LedgerTable";
import { useLanguage } from "@/components/LanguageProvider";
import { SiteHeader } from "@/components/SiteHeader";
import { SummaryView } from "@/components/SummaryView";
import { Tabs } from "@/components/Tabs";
import { fetchCampaignReport, fetchCampaignSummary } from "@/lib/api";
import type { CampaignReport, PlainSummary } from "@/lib/types";

type CampaignViewProps = {
  campaignId: string;
};

const POLL_MS = 3000;
const FINISHED = new Set(["completed", "needs_review"]);
const LEDGER_HEADING = "## Evidence ledger";

function withoutLedgerTable(markdown: string): string {
  const cut = markdown.indexOf(LEDGER_HEADING);
  return cut === -1 ? markdown : markdown.slice(0, cut);
}

export function CampaignView({ campaignId }: CampaignViewProps) {
  const { language, t } = useLanguage();
  const [summary, setSummary] = useState<PlainSummary | null>(null);
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("summary");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let settled = false;
      try {
        const next = await fetchCampaignSummary(campaignId, language);
        if (cancelled) {
          return;
        }
        setSummary(next);
        setError("");
        if (FINISHED.has(next.status.code)) {
          const loaded = await fetchCampaignReport(campaignId);
          if (cancelled) {
            return;
          }
          setReport(loaded);
          settled = true;
        } else if (next.status.code === "failed") {
          settled = true;
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : t("campaign.loadError"));
        }
      }
      if (!cancelled && !settled) {
        timer = window.setTimeout(() => void tick(), POLL_MS);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [campaignId, language, t]);

  const tabs = [
    { id: "summary", label: t("campaign.tab.summary"), content: summary ? <SummaryView summary={summary} /> : null },
    {
      id: "report",
      label: t("campaign.tab.report"),
      content: report ? (
        <div className="space-y-4">
          <h2 className="text-xl text-[#1c1915]">{t("campaign.reportTitle")}</h2>
          <p className="text-sm text-[#5c564e]">{t("campaign.reportHint")}</p>
          <article className="paper space-y-4 text-[17px] leading-8 text-[#1c1915]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{withoutLedgerTable(report.markdown)}</ReactMarkdown>
          </article>
        </div>
      ) : (
        <p className="text-sm text-[#5c564e]">{t("campaign.waiting")}</p>
      ),
    },
    {
      id: "evidence",
      label: t("campaign.tab.evidence"),
      content: report ? (
        <div className="space-y-3">
          <h2 className="text-xl text-[#1c1915]">{t("campaign.evidenceTitle")}</h2>
          <p className="text-sm text-[#5c564e]">{t("campaign.evidenceHint")}</p>
          <LedgerTable ledger={report.ledger} />
        </div>
      ) : (
        <p className="text-sm text-[#5c564e]">{t("campaign.waiting")}</p>
      ),
    },
  ];

  return (
    <>
      <SiteHeader />
      <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-10">
        <Link href="/campaigns" className="text-sm font-semibold text-[#1f6b4a]">
          {t("campaign.back")}
        </Link>
        {error && !summary ? <p className="mt-8 text-sm text-[#9b3d2b]">{error}</p> : null}
        {!summary && !error ? <p className="mt-8 text-sm text-[#5c564e]">{t("campaign.loading")}</p> : null}
        {summary ? (
          <>
            <header className="mt-6 space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <CampaignBadge status={summary.status.code} />
                {summary.status.code === "running" || summary.status.code === "queued" ? (
                  <span className="text-xs text-[#5c564e]">{t("campaign.progress", { finished: summary.progress.finished, total: summary.progress.total })}</span>
                ) : null}
              </div>
              <h1 className="text-3xl leading-tight text-[#1c1915] sm:text-4xl">{summary.title || campaignId}</h1>
              {summary.source ? (
                <p className="text-sm text-[#5c564e]">
                  <span className="font-semibold">{t("campaign.source")}:</span> {summary.source.title}
                  {summary.source.citation ? ` (${summary.source.citation})` : ""}
                </p>
              ) : null}
            </header>
            {summary.error_info ? (
              <div className="mt-8">
                <ErrorNotice info={summary.error_info} />
              </div>
            ) : null}
            <div className="mt-8">
              <Tabs items={tabs} active={tab} onChange={setTab} />
            </div>
          </>
        ) : null}
      </main>
    </>
  );
}
