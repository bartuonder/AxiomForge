"use client";

import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { retryResearch } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";

type RetryResearchProps = {
  threadId: string;
  onDone?: () => void;
};

export function RetryResearch({ threadId, onDone }: RetryResearchProps) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const retry = async () => {
    setBusy(true);
    setError("");
    try {
      await retryResearch(threadId);
      onDone?.();
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void retry()}
          className="rounded-full border border-accent px-4 py-1.5 text-sm font-semibold text-accent hover:bg-accent-tint disabled:opacity-50"
        >
          {busy ? t("campaign.controlBusy") : t("research.retry")}
        </button>
        <span className="text-xs text-muted">{t("research.retryHint")}</span>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
