"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CampaignBadge } from "@/components/CampaignBadge";
import { LedgerTable } from "@/components/LedgerTable";
import { fetchCampaign, fetchCampaignReport } from "@/lib/api";
import type { CampaignReport, CampaignState } from "@/lib/types";

type CampaignViewProps = {
  campaignId: string;
};

const POLL_MS = 3000;
const FINISHED = new Set(["completed", "needs_review"]);
const LEDGER_HEADING = "## Evidence ledger";

function withoutLedgerTable(markdown: string): string {
  const cut = markdown.indexOf(LEDGER_HEADING);
  return cut === -1 ? markdown : markdown.slice(0, cut);
}

export function CampaignView({ campaignId }: CampaignViewProps) {
  const [state, setState] = useState<CampaignState | null>(null);
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let settled = false;
      try {
        const next = await fetchCampaign(campaignId);
        if (cancelled) {
          return;
        }
        setState(next);
        setError("");
        if (FINISHED.has(next.status)) {
          const loaded = await fetchCampaignReport(campaignId);
          if (cancelled) {
            return;
          }
          setReport(loaded);
          settled = true;
        } else if (next.status === "failed") {
          settled = true;
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Campaign request failed");
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
  }, [campaignId]);

  return (
    <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-16">
      <Link href="/campaigns" className="text-sm font-semibold text-[#1f6b4a]">
        Back to campaigns
      </Link>
      <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-[#8a8175] uppercase">Replication campaign</p>
      <h1 className="mt-2 text-4xl text-[#1c1915]">{state?.title || campaignId}</h1>
      {state ? (
        <div className="mt-4 flex items-center gap-3">
          <CampaignBadge status={state.status} />
          <span className="text-xs text-[#8a8175]">{state.id}</span>
        </div>
      ) : null}
      {error && !state ? <p className="mt-8 text-sm text-[#9b3d2b]">{error}</p> : null}
      {state?.error ? <p className="mt-6 text-sm text-[#9b3d2b]">{state.error}</p> : null}
      {state?.issues?.length ? (
        <ul className="mt-6 list-disc space-y-1 pl-5 text-sm text-[#5c4a0c]">
          {state.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
      {state?.verdicts?.length ? (
        <ul className="mt-8 space-y-2">
          {state.verdicts.map((item) => (
            <li key={item.id} className="text-[#1c1915]">
              <span className="font-semibold">{item.id}</span> {item.statement}:{" "}
              <span className="font-semibold text-[#14472f]">{item.verdict.replace("_", " ")}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {state ? (
        <section className="mt-10">
          <h2 className="text-xl text-[#1c1915]">Datasets</h2>
          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {Object.entries(state.datasets).map(([key, item]) => (
              <li
                key={key}
                className="flex items-center justify-between rounded-lg border border-[#d7d0c4] bg-white px-4 py-2 text-sm"
              >
                <span className="text-[#1c1915]">{key}</span>
                <span className={item.status === "failed" ? "text-[#9b3d2b]" : "text-[#5c564e]"}>
                  {item.status}
                  {item.seconds !== undefined ? ` · ${item.seconds.toFixed(0)} s` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {report ? (
        <>
          <article className="paper mt-12 space-y-4 text-[17px] leading-8 text-[#1c1915]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{withoutLedgerTable(report.markdown)}</ReactMarkdown>
          </article>
          <section className="mt-12">
            <h2 className="text-xl text-[#1c1915]">Evidence ledger</h2>
            <div className="mt-4">
              <LedgerTable ledger={report.ledger} />
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
