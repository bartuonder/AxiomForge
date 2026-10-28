"use client";

import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { cancelResearchSession, retryResearchSession } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import { sessionActions } from "@/lib/researchView";

type SessionControlsProps = {
  sessionId: string;
  status: string;
  cancelRequested: boolean;
  onDone: () => void;
};

const BUTTON = "rounded-full border px-4 py-1.5 text-sm font-semibold disabled:opacity-50";

export function SessionControls({ sessionId, status, cancelRequested, onDone }: SessionControlsProps) {
  const { t } = useLanguage();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const actions = sessionActions(status, cancelRequested);

  const send = async (action: (id: string) => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action(sessionId);
      setAsking(false);
      onDone();
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
    } finally {
      setBusy(false);
    }
  };

  if (!actions.cancel && !actions.cancelling && !actions.retry) {
    return null;
  }
  return (
    <div className="mt-6 space-y-2">
      {actions.cancelling ? <p className="text-sm text-muted">{t("research.session.cancelling")}</p> : null}
      {actions.cancel && !asking ? (
        <button type="button" onClick={() => setAsking(true)} className={`${BUTTON} border-danger text-danger hover:bg-danger-tint`}>
          {t("research.session.cancel")}
        </button>
      ) : null}
      {actions.cancel && asking ? (
        <div
          className="space-y-2 rounded-2xl border border-danger-line bg-danger-tint p-4"
          role="alertdialog"
          aria-label={t("research.session.cancel")}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !busy) {
              setAsking(false);
            }
          }}
        >
          <p className="text-sm text-danger-ink">{t("research.session.cancelAsk")}</p>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => void send(cancelResearchSession)} className={`${BUTTON} border-danger bg-danger text-on-solid`}>
              {busy ? t("campaign.controlBusy") : t("research.session.cancelYes")}
            </button>
            <button type="button" autoFocus disabled={busy} onClick={() => setAsking(false)} className={`${BUTTON} border-line text-muted`}>
              {t("research.session.cancelNo")}
            </button>
          </div>
        </div>
      ) : null}
      {actions.retry ? (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" disabled={busy} onClick={() => void send(retryResearchSession)} className={`${BUTTON} border-accent text-accent hover:bg-accent-tint`}>
            {busy ? t("campaign.controlBusy") : t("research.session.retry")}
          </button>
          <span className="text-xs text-muted">{t("research.session.retryHint")}</span>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
