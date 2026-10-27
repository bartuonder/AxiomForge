"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CampaignBadge } from "@/components/CampaignBadge";
import { useLanguage } from "@/components/LanguageProvider";
import { SiteHeader } from "@/components/SiteHeader";
import { VerdictBadge } from "@/components/VerdictBadge";
import { fetchCampaigns, startDemoCampaign } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import { displayTitle, hiddenTestCount, isUserCampaign, visibleCampaigns } from "@/lib/campaignList";
import type { MessageKey } from "@/lib/i18n";
import type { CampaignSummary } from "@/lib/types";

const POLL_MS = 3000;
const ACTIVE = new Set(["queued", "running"]);
const DEMO = "grinsztajn-2022";

const VERDICT_TONES: Record<string, string> = { replicated: "positive", contradicted: "negative", inconclusive: "neutral", partially_replicated: "warning", not_testable: "muted" };
const VERDICT_KEYS: Record<string, { tr: string; en: string }> = {
  replicated: { tr: "Doğrulandı", en: "Confirmed" },
  contradicted: { tr: "Çürütüldü", en: "Refuted" },
  inconclusive: { tr: "Kanıt yetersiz", en: "Not enough evidence" },
  partially_replicated: { tr: "Kısmen doğrulandı", en: "Partly confirmed" },
  not_testable: { tr: "Test edilemedi", en: "Could not be tested" },
};

export default function CampaignsPage() {
  const router = useRouter();
  const { language, t } = useLanguage();
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [showTests, setShowTests] = useState(false);
  const [query, setQuery] = useState("");

  const startDemo = async () => {
    if (!window.confirm(t("list.runDemoConfirm"))) {
      return;
    }
    setStarting(true);
    try {
      router.push(`/campaign/${await startDemoCampaign(DEMO)}`);
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
      setStarting(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let active = true;
      try {
        const items = await fetchCampaigns();
        if (cancelled) {
          return;
        }
        setCampaigns(items);
        setError("");
        active = items.some((item) => ACTIVE.has(item.status));
      } catch (caught) {
        if (!cancelled) {
          setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
        }
      }
      if (!cancelled && active) {
        timer = window.setTimeout(() => void tick(), POLL_MS);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [t]);

  const shown = useMemo(() => visibleCampaigns(campaigns ?? [], showTests, query), [campaigns, showTests, query]);
  const hidden = hiddenTestCount(campaigns ?? []);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-10">
        <h1 className="text-4xl text-[#1c1915]">{t("list.title")}</h1>
        <p className="mt-2 text-[#5c564e]">{t("list.subtitle")}</p>

        <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("list.search")}
            aria-label={t("list.search")}
            className="h-11 flex-1 rounded-full border border-[#d7d0c4] bg-white px-5 text-sm outline-none focus:border-[#1f6b4a]"
          />
          {hidden > 0 || showTests ? (
            <label className="flex cursor-pointer items-center gap-2 text-sm text-[#5c564e]">
              <input type="checkbox" checked={showTests} onChange={(event) => setShowTests(event.target.checked)} className="h-4 w-4 accent-[#1f6b4a]" />
              {t("list.showTests")} ({hidden})
            </label>
          ) : null}
        </div>

        <button
          type="button"
          disabled={starting}
          onClick={() => void startDemo()}
          className="mt-6 h-11 cursor-pointer rounded-full bg-[#1f6b4a] px-5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#d5d0c6] disabled:text-[#6f675e]"
        >
          {starting ? t("list.starting") : t("list.runDemo")}
        </button>

        {error ? <p className="mt-6 text-sm text-[#9b3d2b]">{error}</p> : null}
        {campaigns && campaigns.length === 0 ? <p className="mt-8 text-sm text-[#5c564e]">{t("list.empty")}</p> : null}
        {campaigns && campaigns.length > 0 && shown.length === 0 ? (
          <p className="mt-8 text-sm text-[#5c564e]">{!showTests && hidden === campaigns.length && !query.trim() ? t("list.onlyTests", { count: hidden }) : t("list.emptyFiltered")}</p>
        ) : null}

        <ul className="mt-8 space-y-4">
          {shown.map((campaign) => (
            <li key={campaign.id}>
              <Link href={`/campaign/${campaign.id}`} className="block rounded-2xl border border-[#d7d0c4] bg-white p-5 hover:border-[#1f6b4a]">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-lg leading-snug text-[#1c1915]">{displayTitle(campaign, t("list.unnamed"))}</p>
                  <CampaignBadge status={campaign.status} />
                </div>
                {campaign.statement ? <p className="mt-1 text-sm text-[#5c564e]">{campaign.statement}</p> : null}
                {campaign.verdicts.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {campaign.verdicts.map((item) => (
                      <span key={item.id} className="flex items-center gap-1 text-xs text-[#5c564e]">
                        <span className="font-semibold">{item.id}</span>
                        <VerdictBadge label={VERDICT_KEYS[item.verdict]?.[language] ?? item.verdict} tone={VERDICT_TONES[item.verdict] ?? "muted"} />
                      </span>
                    ))}
                  </div>
                ) : null}
                <p className="mt-3 text-xs text-[#8a8175]">
                  {t("list.progress", { finished: campaign.finished, total: campaign.datasets })}
                  {campaign.failed ? ` · ${t("list.failedSets", { count: campaign.failed })}` : ""}
                  {!isUserCampaign(campaign.origin) ? ` · ${t("list.test")}` : ` · ${t(`list.from.${campaign.origin}` as MessageKey)}`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
