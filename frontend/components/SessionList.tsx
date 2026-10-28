"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { SiteHeader } from "@/components/SiteHeader";
import { StartSession } from "@/components/StartSession";
import { VerdictBadge } from "@/components/VerdictBadge";
import { fetchResearchSessions } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import type { MessageKey } from "@/lib/i18n";
import { sessionTone } from "@/lib/researchView";
import type { SessionSummary } from "@/lib/types";

export function SessionCards({ sessions }: { sessions: SessionSummary[] }) {
  const { names, t } = useLanguage();
  if (sessions.length === 0) {
    return <p className="mt-8 text-sm text-muted">{t("research.list.empty")}</p>;
  }
  return (
    <ul className="mt-8 space-y-4">
      {sessions.map((item) => (
        <li key={item.id}>
          <Link href={`/research/${encodeURIComponent(item.id)}`} className="block rounded-2xl border border-line bg-card p-5 hover:border-accent">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="font-semibold text-ink">{item.id}</span>
              <VerdictBadge label={t(`research.status.${item.status}` as MessageKey)} tone={sessionTone(item.status)} />
            </div>
            <p className="mt-2 text-sm text-muted">{t("research.list.models", { models: item.models.map((model) => names.models[model] ?? model).join(", ") })}</p>
            <p className="mt-1 text-sm text-ink">{t("research.list.summary", { registered: item.registered, confirmed: item.counts.confirmed })}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function SessionList() {
  const { t } = useLanguage();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchResearchSessions()
      .then((items) => {
        if (!cancelled) {
          setSessions(items);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-10">
        <h1 className="text-4xl text-ink">{t("research.list.title")}</h1>
        <p className="mt-2 text-muted">{t("research.list.subtitle")}</p>
        <StartSession />
        {error ? <p className="mt-8 text-sm text-danger">{error}</p> : null}
        {sessions ? <SessionCards sessions={sessions} /> : null}
      </main>
    </>
  );
}
