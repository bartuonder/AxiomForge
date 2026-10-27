"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ResearchStatus } from "@/components/ResearchStatus";
import { fetchReport, fetchResearch } from "@/lib/api";
import { STEP_LABELS, type ResearchSnapshot } from "@/lib/types";

type PaperViewProps = {
  threadId: string;
};

const POLL_MS = 2000;
const FINISHED = new Set(["completed", "needs_review"]);
const STOPPED = new Set(["failed", "rejected"]);

export function PaperView({ threadId }: PaperViewProps) {
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
        const next = await fetchResearch(threadId);
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
          setError(next.error || `Research ${next.status}`);
          settled = true;
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Report is not ready");
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
  }, [threadId]);

  const running = snapshot !== null && !FINISHED.has(snapshot.status) && !STOPPED.has(snapshot.status);

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-16">
      <Link href="/" className="text-sm font-semibold text-accent">
        Back to console
      </Link>
      <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-faint uppercase">Workshop paper</p>
      <h1 className="mt-2 text-4xl text-ink">Research report</h1>
      {snapshot && !STOPPED.has(snapshot.status) ? <ResearchStatus snapshot={snapshot} /> : null}
      {running ? (
        <p className="mt-8 text-sm text-muted">
          The research is still running: {STEP_LABELS[snapshot.active_step] ?? snapshot.active_step}.
        </p>
      ) : null}
      {error && !markdown ? <p className="mt-8 text-sm text-danger">{error}</p> : null}
      {markdown ? (
        <article className="paper mt-10 space-y-4 text-[17px] leading-8 text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </article>
      ) : null}
    </main>
  );
}
