"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgentTimeline } from "@/components/AgentTimeline";
import { ApprovalDialog } from "@/components/ApprovalDialog";
import { CampaignApprovalDialog } from "@/components/CampaignApprovalDialog";
import { ResearchForm } from "@/components/ResearchForm";
import { approvePlan, fetchResearch, startResearch } from "@/lib/api";
import type { ResearchMode, ResearchSnapshot } from "@/lib/types";

const EXPERIMENT_STEPS = [
  { id: "literature_node", phase: "pending" as const },
  { id: "planner_node", phase: "pending" as const },
  { id: "experiment_node", phase: "pending" as const },
  { id: "verifier_node", phase: "pending" as const },
  { id: "report_node", phase: "pending" as const },
  { id: "consistency_checker_node", phase: "pending" as const },
];
const CAMPAIGN_STEPS = [
  { id: "literature_node", phase: "pending" as const },
  { id: "campaign_planner_node", phase: "pending" as const },
  { id: "campaign_node", phase: "pending" as const },
  { id: "meta_report_node", phase: "pending" as const },
  { id: "meta_consistency_node", phase: "pending" as const },
];

export default function Home() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ResearchMode>("experiment");
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
        const next = await fetchResearch(threadId);
        if (cancelled) {
          return;
        }
        setSnapshot(next);
        if (next.status === "completed" || next.status === "needs_review") {
          router.push(`/result/${threadId}`);
        }
        if (next.error) {
          setError(next.error);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Status request failed");
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [router, threadId]);

  async function onStart() {
    setError("");
    setBusy(true);
    setSnapshot(null);
    try {
      const started = await startResearch(query.trim(), mode);
      setThreadId(started.thread_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start research");
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
      setError(caught instanceof Error ? caught.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  const steps = snapshot?.steps?.length ? snapshot.steps : mode === "campaign" ? CAMPAIGN_STEPS : EXPERIMENT_STEPS;
  const campaign = snapshot?.mode === "campaign";
  const candidates = snapshot?.campaign_specs ?? [];
  const paused = snapshot?.status === "paused" && !campaign && snapshot.hypotheses.length > 0;
  const campaignPaused = snapshot?.status === "paused" && campaign && candidates.length > 0;
  const runLocked = Boolean(threadId) && snapshot?.status !== "rejected" && snapshot?.status !== "failed";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-12 px-6 py-16">
      <header className="space-y-3 text-center">
        <p className="text-xs font-semibold tracking-[0.18em] text-[#1f6b4a] uppercase">AxiomForge</p>
        <h1 className="text-4xl text-[#1c1915]">Research console</h1>
        <p className="text-[#5c564e]">Literature, plan, experiment, verification, then the paper.</p>
        <Link href="/campaigns" className="inline-block text-sm font-semibold text-[#1f6b4a]">
          Replication campaigns
        </Link>
      </header>
      <ResearchForm
        query={query}
        mode={mode}
        busy={busy || runLocked}
        onQueryChange={setQuery}
        onModeChange={setMode}
        onSubmit={() => void onStart()}
      />
      {error ? <p className="text-center text-sm text-[#9b3d2b]">{error}</p> : null}
      <AgentTimeline steps={steps} />
      {paused ? (
        <ApprovalDialog
          hypotheses={snapshot.hypotheses}
          specs={snapshot.experiment_specs}
          busy={busy}
          onDecide={(decision, selected) => void onDecide(decision, selected)}
        />
      ) : null}
      {campaignPaused ? (
        <CampaignApprovalDialog
          candidates={candidates}
          busy={busy}
          onDecide={(decision, selected) => void onDecide(decision, selected)}
        />
      ) : null}
      {snapshot?.campaign_id ? (
        <p className="text-center text-sm">
          <Link href={`/campaign/${snapshot.campaign_id}`} className="font-semibold text-[#1f6b4a]">
            Follow the campaign
          </Link>
        </p>
      ) : null}
      {snapshot?.status === "rejected" ? (
        <p className="text-center text-sm text-[#5c564e]">
          Plan rejected. The {campaign ? "campaign" : "experiment"} did not start.
        </p>
      ) : null}
    </main>
  );
}
