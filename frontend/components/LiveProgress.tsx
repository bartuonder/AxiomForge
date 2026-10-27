"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { etaMinutes } from "@/lib/format";
import type { PlainSummary } from "@/lib/types";

export function LiveProgress({ summary }: { summary: PlainSummary }) {
  const { t } = useLanguage();
  const { live, progress, status } = summary;
  const names = live.running.map((item) => item.label).join(", ");
  const running = status.code === "running";
  let eta = t("campaign.etaUnknown");
  if (live.eta_seconds !== null) {
    const minutes = etaMinutes(live.eta_seconds);
    eta = minutes === 0 ? t("campaign.etaShort") : t("campaign.eta", { minutes });
  }
  return (
    <div className="space-y-3">
      <p className="text-[#5c564e]">{running ? t("campaign.waiting") : t("campaign.queuedNote")}</p>
      <div className="h-3 overflow-hidden rounded-full bg-[#ece6da]" aria-hidden="true">
        <div className="h-3 rounded-full bg-[#1f6b4a] transition-all" style={{ width: `${progress.percent}%` }} />
      </div>
      <p className="text-sm text-[#5c564e]">{t("campaign.progress", { finished: progress.finished, total: progress.total })}</p>
      {names ? <p className="text-sm text-[#5c564e]">{t("campaign.runningNow", { names })}</p> : null}
      {running ? <p className="text-sm text-[#5c564e]">{eta}</p> : null}
    </div>
  );
}
