"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { ResearchTable } from "@/components/ResearchTable";
import { SessionControls } from "@/components/SessionControls";
import { SiteHeader } from "@/components/SiteHeader";
import { VerdictBadge } from "@/components/VerdictBadge";
import { fetchResearchSession, fetchResearchSessionReport } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import { downloadText, slug } from "@/lib/download";
import type { MessageKey } from "@/lib/i18n";
import { isActiveSession, mergeRows, phaseMessage, progressPercent, sessionTone, showProgress } from "@/lib/researchView";
import type { SessionDetail } from "@/lib/types";

const POLL_MS = 5000;

export function SessionDetails({ detail }: { detail: SessionDetail }) {
  const { names, t } = useLanguage();
  const { summary, session, intact } = detail;
  const rows = mergeRows(session.hypotheses, session.confirmations);
  const phase = phaseMessage(summary.status, summary.phase);
  const datasetList = (keys: string[]) => keys.map((key) => names.datasets[key] ?? key).join(", ");
  return (
    <>
      <header className="mt-6 space-y-3">
        <VerdictBadge label={t(`research.status.${summary.status}` as MessageKey)} tone={sessionTone(summary.status)} />
        <h1 className="text-3xl leading-tight text-ink sm:text-4xl">{t("research.session.title", { id: summary.id })}</h1>
        <p className="text-sm text-muted">{t("research.list.models", { models: summary.models.map((model) => names.models[model] ?? model).join(", ") })}</p>
        {summary.reason ? <p className="text-sm text-danger">{summary.reason}</p> : null}
        {session.stale ? <p className="text-sm text-danger">{t("research.session.stale")}</p> : null}
        {phase ? <p className="text-sm text-muted">{t(phase as MessageKey)}</p> : null}
        {showProgress(summary.status, summary.progress) && summary.progress ? (
          <div className="space-y-2">
            <div
              className="h-3 overflow-hidden rounded-full bg-track"
              role="progressbar"
              aria-label={t("research.progress.label")}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progressPercent(summary.progress)}
            >
              <div className="h-3 rounded-full bg-accent transition-all" style={{ width: `${progressPercent(summary.progress)}%` }} />
            </div>
            <p className="text-sm text-muted">
              {t("research.progress.count", { finished: summary.progress.finished + summary.progress.failed, total: summary.progress.total })}
              {summary.progress.failed > 0 ? ` ${t("research.progress.failed", { failed: summary.progress.failed })}` : ""}
            </p>
            {summary.progress.running.length > 0 ? (
              <p className="text-sm text-muted">{t("research.progress.running", { names: summary.progress.running.map((key) => names.datasets[key] ?? key).join(", ") })}</p>
            ) : null}
          </div>
        ) : null}
      </header>

      <section className="mt-8 space-y-3">
        <h2 className="text-xl text-ink">{t("research.how.title")}</h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm leading-6 text-muted">
          {([1, 2, 3, 4] as const).map((step) => (
            <li key={step}>{t(`research.how.${step}` as MessageKey, { explore: summary.explore.length, confirm: summary.confirm.length })}</li>
          ))}
        </ol>
      </section>

      {summary.status === "queued" ? null : (
      <section className="mt-8 space-y-3">
        <h2 className="text-xl text-ink">{t("research.result.title")}</h2>
        <p className="text-lg text-ink">
          {t("research.result.counts", {
            registered: summary.registered,
            confirmed: summary.counts.confirmed,
            reversed: summary.counts.reversed,
            notConfirmed: summary.counts.not_confirmed,
            notTestable: summary.counts.not_testable,
          })}
        </p>
        <p className="text-sm text-muted">{t("research.result.budget", { budget: summary.budget })}</p>
        <p className={`text-sm font-semibold ${intact ? "text-accent" : "text-danger"}`} role={intact ? undefined : "alert"}>
          {intact ? t("research.integrity.ok") : t("research.integrity.bad")}
        </p>
      </section>
      )}

      {rows.length > 0 ? (
        <section className="mt-8 space-y-3">
          <h2 className="text-xl text-ink">{t("research.table.title")}</h2>
          <ResearchTable rows={rows} />
        </section>
      ) : null}

      <section className="mt-8 grid gap-6 sm:grid-cols-2">
        <div className="space-y-2">
          <h2 className="text-xl text-ink">{t("research.datasets.title")}</h2>
          <p className="text-sm text-muted">
            <span className="font-semibold text-ink">{t("research.datasets.explore")}:</span> {datasetList(summary.explore)}
          </p>
          <p className="text-sm text-muted">
            <span className="font-semibold text-ink">{t("research.datasets.confirm")}:</span> {datasetList(summary.confirm)}
          </p>
        </div>
        {session.skipped && session.skipped.length > 0 ? (
          <div className="space-y-2">
            <h2 className="text-xl text-ink">{t("research.skipped.title")}</h2>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
              {session.skipped.map((item) => (
                <li key={`${item.stage}-${item.statement}`}>
                  {item.statement}: {item.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </>
  );
}

export function SessionView({ sessionId }: { sessionId: string }) {
  const { t } = useLanguage();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [error, setError] = useState("");
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let active = true;
      try {
        const next = await fetchResearchSession(sessionId);
        if (cancelled) {
          return;
        }
        setDetail(next);
        setError("");
        active = isActiveSession(next.summary.status);
      } catch (caught) {
        if (!cancelled) {
          setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("research.session.loadError"));
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
  }, [sessionId, t, reloads]);

  const download = async () => {
    const markdown = await fetchResearchSessionReport(sessionId);
    downloadText(`${slug(sessionId) || "session"}-report.md`, markdown);
  };

  return (
    <>
      <SiteHeader />
      <main className="mx-auto min-h-screen w-full max-w-5xl px-6 py-10">
        <Link href="/research" className="text-sm font-semibold text-accent">
          {t("research.session.back")}
        </Link>
        {error && !detail ? <p className="mt-8 text-sm text-danger">{error}</p> : null}
        {!detail && !error ? <p className="mt-8 text-sm text-muted">{t("research.session.loading")}</p> : null}
        {detail ? (
          <>
            <SessionDetails detail={detail} />
            <SessionControls
              sessionId={sessionId}
              status={detail.summary.status}
              cancelRequested={Boolean(detail.session.cancel_requested)}
              onDone={() => setReloads((count) => count + 1)}
            />
            {!isActiveSession(detail.summary.status) ? (
              <button type="button" onClick={() => void download()} className="mt-8 rounded-full border border-accent px-4 py-1.5 text-sm font-semibold text-accent hover:bg-accent-tint">
                {t("research.download")}
              </button>
            ) : null}
          </>
        ) : null}
      </main>
    </>
  );
}
