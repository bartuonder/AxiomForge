"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useLanguage } from "@/components/LanguageProvider";
import { ResearchStatus } from "@/components/ResearchStatus";
import { SiteHeader } from "@/components/SiteHeader";
import { fetchReport, fetchResearch } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import type { MessageKey } from "@/lib/i18n";
import type { ResearchSnapshot } from "@/lib/types";

type PaperViewProps = {
  threadId: string;
};

const POLL_MS = 2000;
const FINISHED = new Set(["completed", "needs_review"]);
const STOPPED = new Set(["failed", "rejected"]);

export function PaperView({ threadId }: PaperViewProps) {
  const { language, t } = useLanguage();
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);

  useEffect(() => {
    if (!threadId) {
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let settled = false;
      try {
        const next = await fetchResearch(threadId, language);
        if (cancelled) {
          return;
        }
        setSnapshot(next);
        if (FINISHED.has(next.status)) {
          const report = await fetchReport(threadId);
          if (cancelled) {
            return;
          }
          setMarkdown(report);
          setError("");
          settled = true;
        } else if (STOPPED.has(next.status)) {
          setError(next.error_info ? "" : next.error || t("paper.stopped", { status: next.status }));
          settled = true;
        }
      } catch (caught) {
        if (!cancelled) {
          setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("paper.notReady"));
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
  }, [threadId, language, t]);

  const running = snapshot !== null && !FINISHED.has(snapshot.status) && !STOPPED.has(snapshot.status);

  const stepKey = snapshot ? (`step.${snapshot.active_step}` as MessageKey) : null;
  const step = snapshot && stepKey ? (t(stepKey) === stepKey ? snapshot.active_step : t(stepKey)) : "";

  return (
    <>
      <SiteHeader />
      <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-10">
        <Link href="/" className="text-sm font-semibold text-accent">
          {t("paper.back")}
        </Link>
        <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-faint uppercase">{t("paper.kicker")}</p>
        <h1 className="mt-2 text-4xl text-ink">{t("paper.title")}</h1>
        <p className="mt-2 text-sm text-muted">{t("paper.language")}</p>
        {snapshot && !STOPPED.has(snapshot.status) ? <ResearchStatus snapshot={snapshot} /> : null}
        {running ? <p className="mt-8 text-sm text-muted">{t("paper.running", { step })}</p> : null}
        {snapshot && STOPPED.has(snapshot.status) && snapshot.error_info ? (
          <div className="mt-8">
            <ErrorNotice info={snapshot.error_info} />
          </div>
        ) : null}
        {error && !markdown ? <ErrorNotice fallback={error} /> : null}
        {markdown ? (
          <article className="paper mt-10 space-y-4 text-[17px] leading-8 text-ink">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </article>
        ) : null}
      </main>
    </>
  );
}
