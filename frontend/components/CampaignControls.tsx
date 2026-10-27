"use client";

import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { cancelCampaign, retryCampaign } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import type { PlainSummary } from "@/lib/types";

type CampaignControlsProps = {
  summary: PlainSummary;
  onDone: () => void;
};

const BUTTON = "rounded-full border px-4 py-1.5 text-sm font-semibold disabled:opacity-50";

export function CampaignControls({ summary, onDone }: CampaignControlsProps) {
  const { t } = useLanguage();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { actions, live, recoveries } = summary;

  const send = async (action: (id: string) => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action(summary.campaign_id);
      setAsking(false);
      onDone();
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
    } finally {
      setBusy(false);
    }
  };

  if (!actions.cancel && !actions.retry && recoveries === 0) {
    return null;
  }
  return (
    <div className="space-y-2">
      {actions.cancel && live.cancel_requested ? <p className="text-sm text-[#5c564e]">{t("campaign.cancelling")}</p> : null}
      {actions.cancel && !live.cancel_requested && !asking ? (
        <button type="button" onClick={() => setAsking(true)} className={`${BUTTON} border-[#9b3d2b] text-[#9b3d2b] hover:bg-[#faeeea]`}>
          {t("campaign.cancel")}
        </button>
      ) : null}
      {actions.cancel && !live.cancel_requested && asking ? (
        <div className="space-y-2 rounded-2xl border border-[#d9a99e] bg-[#faeeea] p-4" role="alertdialog">
          <p className="text-sm text-[#6e2a1c]">{t("campaign.cancelAsk")}</p>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => void send(cancelCampaign)} className={`${BUTTON} border-[#9b3d2b] bg-[#9b3d2b] text-white`}>
              {busy ? t("campaign.controlBusy") : t("campaign.cancelYes")}
            </button>
            <button type="button" disabled={busy} onClick={() => setAsking(false)} className={`${BUTTON} border-[#d7d0c4] text-[#5c564e]`}>
              {t("campaign.cancelNo")}
            </button>
          </div>
        </div>
      ) : null}
      {actions.retry ? (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" disabled={busy} onClick={() => void send(retryCampaign)} className={`${BUTTON} border-[#1f6b4a] text-[#1f6b4a] hover:bg-[#eef6f1]`}>
            {busy ? t("campaign.controlBusy") : t("campaign.retry")}
          </button>
          <span className="text-xs text-[#5c564e]">{t("campaign.retryHint")}</span>
        </div>
      ) : null}
      {recoveries > 0 ? <p className="text-xs text-[#5c564e]">{t("campaign.restarted", { count: recoveries })}</p> : null}
      {error ? (
        <p role="alert" className="text-sm text-[#9b3d2b]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
