"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgentTimeline } from "@/components/AgentTimeline";
import { ApprovalDialog } from "@/components/ApprovalDialog";
import { CampaignApprovalDialog } from "@/components/CampaignApprovalDialog";
import { ErrorNotice } from "@/components/ErrorNotice";
import { useLanguage } from "@/components/LanguageProvider";
import { ResearchForm } from "@/components/ResearchForm";
import { SiteHeader } from "@/components/SiteHeader";
import { approvePlan, fetchResearch, startResearch } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import type { ResearchMode, ResearchSnapshot } from "@/lib/types";

const EXPERIMENT_STEPS = ["literature_node", "planner_node", "experiment_node", "verifier_node", "report_node", "consistency_checker_node"];
const CAMPAIGN_STEPS = ["literature_node", "campaign_planner_node", "campaign_node", "meta_report_node", "meta_consistency_node"];

const HOW_STEPS = [
  { title: "how.step1.title", text: "how.step1.text" },
  { title: "how.step2.title", text: "how.step2.text" },
  { title: "how.step3.title", text: "how.step3.text" },
] as const;

export default function Home() {
  const router = useRouter();
  const { language, t } = useLanguage();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ResearchMode>("campaign");
  const [threadId, setThreadId] = useState("");
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!threadId) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await fetchResearch(threadId, language);
        if (cancelled) {
          return;
        }
        setSnapshot(next);
        if (next.status === "completed" || next.status === "needs_review") {
          router.push(next.mode === "campaign" && next.campaign_id ? `/campaign/${next.campaign_id}` : `/result/${threadId}`);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [router, threadId, language, t]);

  async function onStart() {
    setError("");
    setBusy(true);
    setSnapshot(null);
    try {
      const started = await startResearch(query.trim(), mode);
      setThreadId(started.thread_id);
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
    } finally {
      setBusy(false);
    }
  }

  async function onDecide(decision: "Y" | "N", selected?: number) {
    if (!threadId) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      await approvePlan(threadId, decision, selected);
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
    } finally {
      setBusy(false);
    }
  }

  const campaign = (snapshot?.mode ?? mode) === "campaign";
  const steps = snapshot?.steps?.length
    ? snapshot.steps
    : (campaign ? CAMPAIGN_STEPS : EXPERIMENT_STEPS).map((id) => ({ id, phase: "pending" as const }));
  const candidates = snapshot?.campaign_specs ?? [];
  const paused = snapshot?.status === "paused" && !campaign && snapshot.hypotheses.length > 0;
  const campaignPaused = snapshot?.status === "paused" && campaign && candidates.length > 0;
  const failed = snapshot?.status === "failed";
  const runLocked = Boolean(threadId) && snapshot?.status !== "rejected" && !failed;
  const showProgress = Boolean(threadId) && !failed;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-12 px-6 py-12">
        <section className="mx-auto max-w-3xl space-y-4 text-center">
          <h1 className="text-4xl leading-tight text-[#1c1915] sm:text-5xl">{t("hero.title")}</h1>
          <p className="text-lg leading-8 text-[#5c564e]">{t("hero.subtitle")}</p>
        </section>

        {!threadId ? (
          <section className="grid gap-4 sm:grid-cols-3" aria-label={t("how.title")}>
            {HOW_STEPS.map((step, index) => (
              <div key={step.title} className="rounded-2xl border border-[#e4ddd2] bg-white p-5">
                <p className="text-xs font-semibold tracking-[0.16em] text-[#1f6b4a]">{index + 1}</p>
                <h2 className="mt-1 text-lg text-[#1c1915]">{t(step.title)}</h2>
                <p className="mt-2 text-sm leading-6 text-[#5c564e]">{t(step.text)}</p>
              </div>
            ))}
          </section>
        ) : null}

        <ResearchForm query={query} mode={mode} busy={busy || runLocked} onQueryChange={setQuery} onModeChange={setMode} onSubmit={() => void onStart()} />

        {failed ? <ErrorNotice info={snapshot?.error_info} fallback={snapshot?.error} /> : null}
        {error && !failed ? <ErrorNotice fallback={error} /> : null}

        {showProgress ? (
          <section className="space-y-6">
            <div className="text-center">
              <h2 className="text-2xl text-[#1c1915]">{t("progress.title")}</h2>
              <p className="mt-1 text-sm text-[#5c564e]">{t("progress.hint")}</p>
            </div>
            <AgentTimeline steps={steps} />
          </section>
        ) : null}

        {paused ? <ApprovalDialog hypotheses={snapshot.hypotheses} specs={snapshot.experiment_specs} busy={busy} onDecide={(decision, selected) => void onDecide(decision, selected)} /> : null}
        {campaignPaused ? <CampaignApprovalDialog candidates={candidates} busy={busy} onDecide={(decision, selected) => void onDecide(decision, selected)} /> : null}
        {snapshot?.campaign_id ? (
          <p className="text-center text-sm">
            <Link href={`/campaign/${snapshot.campaign_id}`} className="font-semibold text-[#1f6b4a]">
              {t("progress.follow")}
            </Link>
          </p>
        ) : null}
        {snapshot?.status === "rejected" ? <p className="text-center text-sm text-[#5c564e]">{t("progress.rejected")}</p> : null}
      </main>
    </>
  );
}
