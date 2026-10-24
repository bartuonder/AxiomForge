"use client";

import { useState } from "react";
import type { CampaignCandidate } from "@/lib/types";

type CampaignApprovalDialogProps = {
  candidates: CampaignCandidate[];
  busy: boolean;
  onDecide: (decision: "Y" | "N", selected?: number) => void;
};

const METRIC_NAMES: Record<string, string> = { roc_auc: "ROC-AUC", pr_auc: "PR-AUC", f1: "F1" };

function minutes(seconds: number): string {
  return `${Math.max(1, Math.round(seconds / 60))} min`;
}

export function CampaignApprovalDialog({ candidates, busy, onDecide }: CampaignApprovalDialogProps) {
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <section className="mx-auto w-full max-w-3xl rounded-3xl border border-[#d7d0c4] bg-white p-6 shadow-[0_20px_60px_rgba(28,25,21,0.08)]">
      <p className="text-xs font-semibold tracking-[0.16em] text-[#1f6b4a] uppercase">Campaign plan paused</p>
      <h2 className="mt-2 text-2xl text-[#1c1915]">Choose the campaign to run</h2>
      <p className="mt-2 text-sm text-[#5c564e]">
        Only the campaign you pick runs. It uses the sandbox for the estimated time and no language model.
      </p>
      <fieldset className="mt-5 space-y-3" disabled={busy}>
        <legend className="sr-only">Campaigns</legend>
        {candidates.map((candidate, index) => {
          const { spec, estimate, evidence } = candidate;
          const checked = selected === index;
          return (
            <label
              key={`${index}-${spec.title}`}
              className={`flex cursor-pointer gap-3 rounded-2xl border px-4 py-3 text-sm leading-6 text-[#1c1915] ${
                checked ? "border-[#1f6b4a] bg-[#eef6f1]" : "border-transparent bg-[#f6f1e8]"
              }`}
            >
              <input
                type="radio"
                name="campaign"
                value={index}
                checked={checked}
                onChange={() => setSelected(index)}
                className="mt-1.5 h-4 w-4 shrink-0 accent-[#1f6b4a]"
              />
              <span className="block space-y-2">
                <span className="block font-semibold">
                  <span className="mr-2 text-[#1f6b4a]">{index + 1}.</span>
                  {spec.title}
                </span>
                {spec.claims.map((claim) => (
                  <span key={claim.id} className="block">
                    <span className="font-semibold">{claim.id}</span> {claim.statement}
                    <span className="block text-xs text-[#5c564e]">
                      {claim.subject.join(" + ")} against {claim.other.join(" + ")} on{" "}
                      {claim.metrics.map((metric) => METRIC_NAMES[metric] ?? metric).join(", ")}
                    </span>
                  </span>
                ))}
                <span className="block text-xs text-[#5c564e]">
                  Models: {spec.models.join(", ")} · {estimate.datasets} datasets ({spec.datasets.join(", ")})
                </span>
                <span className="block text-xs text-[#5c564e]">
                  About {minutes(estimate.estimated_seconds)} (up to {minutes(estimate.worst_case_seconds)} with retries), {estimate.sandboxes} sandboxes (up to {estimate.max_sandboxes})
                </span>
                {spec.source?.title ? (
                  <span className="block text-xs text-[#5c564e]">Source: {spec.source.title}</span>
                ) : null}
                {evidence.map((item) => (
                  <span key={`${item.claim}-${item.quote}`} className="block text-xs italic text-[#5c564e]">
                    {item.claim}: “{item.quote}”
                  </span>
                ))}
                {candidate.repeats?.length ? (
                  <span className="block text-xs font-semibold text-[#5c4a0c]">
                    Already run: {candidate.repeats.join(", ")}. Running it again repeats that work.
                  </span>
                ) : null}
                {spec.source?.deviations?.length ? (
                  <span className="block text-xs text-[#5c564e]">
                    Differs from the source in {spec.source.deviations.length} documented ways.
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </fieldset>
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          disabled={busy || selected === null}
          onClick={() => {
            if (selected !== null) {
              onDecide("Y", selected);
            }
          }}
          className="h-11 rounded-full bg-[#1f6b4a] px-5 text-sm font-semibold text-white disabled:bg-[#8aa898]"
        >
          Onayla (Y)
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide("N")}
          className="h-11 rounded-full border border-[#d7d0c4] px-5 text-sm font-semibold text-[#1c1915] disabled:text-[#8a8175]"
        >
          Reddet (N)
        </button>
      </div>
    </section>
  );
}
