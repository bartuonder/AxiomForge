"use client";

import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { Term } from "@/components/Term";
import { minutes } from "@/lib/format";
import { sourceLabel, tuningLabel } from "@/lib/campaignView";
import type { CampaignCandidate } from "@/lib/types";

type CampaignApprovalDialogProps = {
  candidates: CampaignCandidate[];
  busy: boolean;
  onDecide: (decision: "Y" | "N", selected?: number) => void;
};

export function CampaignApprovalDialog({ candidates, busy, onDecide }: CampaignApprovalDialogProps) {
  const { t, names } = useLanguage();
  const [selected, setSelected] = useState<number | null>(null);
  const model = (key: string) => names.models[key] ?? key;
  return (
    <section className="mx-auto w-full max-w-3xl rounded-3xl border border-[#d7d0c4] bg-white p-6 shadow-[0_20px_60px_rgba(28,25,21,0.08)]">
      <h2 className="text-2xl text-[#1c1915]">{t("approval.title")}</h2>
      <p className="mt-2 text-sm text-[#5c564e]">{t("approval.intro")}</p>
      <fieldset className="mt-5 space-y-3" disabled={busy}>
        <legend className="sr-only">{t("approval.title")}</legend>
        {candidates.map((candidate, index) => {
          const { spec, estimate, evidence } = candidate;
          const checked = selected === index;
          const tuned = tuningLabel(spec.tuning);
          const source = sourceLabel(spec.source);
          return (
            <label
              key={`${index}-${spec.title}`}
              className={`flex cursor-pointer gap-3 rounded-2xl border px-4 py-4 text-sm leading-6 text-[#1c1915] ${
                checked ? "border-[#1f6b4a] bg-[#eef6f1]" : "border-[#e4ddd2] bg-[#faf8f3]"
              }`}
            >
              <input type="radio" name="campaign" value={index} checked={checked} onChange={() => setSelected(index)} className="mt-1.5 h-4 w-4 shrink-0 accent-[#1f6b4a]" />
              <span className="block space-y-3">
                <span className="block text-base font-semibold">
                  <span className="mr-2 text-[#1f6b4a]">{index + 1}.</span>
                  {spec.title}
                </span>
                {spec.claims.map((claim) => (
                  <span key={claim.id} className="block">
                    <span className="block text-xs font-semibold tracking-[0.1em] text-[#8a8175] uppercase">
                      <Term id="claim">{t("approval.claim")}</Term>
                    </span>
                    {claim.statement}
                    <span className="block text-xs text-[#5c564e]">
                      {claim.subject.map(model).join(" + ")} / {claim.other.map(model).join(" + ")} · {claim.metrics.map((metric) => names.metrics[metric] ?? metric).join(", ")}
                    </span>
                  </span>
                ))}
                <span className="block text-xs text-[#5c564e]">
                  {t("approval.models")}: {spec.models.map(model).join(", ")}
                </span>
                <span className="block text-xs text-[#5c564e]">
                  <Term id="dataset">{t("approval.datasets", { count: estimate.datasets })}</Term>
                </span>
                <span className="block text-xs text-[#5c564e]">{t("approval.time", { minutes: minutes(estimate.estimated_seconds), worst: minutes(estimate.worst_case_seconds) })}</span>
                {tuned ? (
                  <span className="block text-xs font-semibold text-[#14472f]">
                    <Term id="tuned">{t("approval.tuned")}</Term>
                  </span>
                ) : null}
                {source ? (
                  <span className="block text-xs text-[#5c564e]">
                    {t("approval.source")}: {source}
                  </span>
                ) : null}
                {evidence.map((item) => (
                  <span key={`${item.claim}-${item.quote}`} className="block text-xs italic text-[#5c564e]">
                    {t("approval.quote")}: “{item.quote}”
                  </span>
                ))}
                {candidate.repeats?.length ? (
                  <span className="block text-xs font-semibold text-[#5c4a0c]">{t("approval.repeat", { names: candidate.repeats.join(", ") })}</span>
                ) : null}
                {spec.source?.deviations?.length ? (
                  <span className="block text-xs text-[#8a8175]">{t("approval.deviations", { count: spec.source.deviations.length })}</span>
                ) : null}
              </span>
            </label>
          );
        })}
      </fieldset>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy || selected === null}
          onClick={() => {
            if (selected !== null) {
              onDecide("Y", selected);
            }
          }}
          className="h-11 rounded-full bg-[#1f6b4a] px-6 text-sm font-semibold text-white disabled:bg-[#8aa898]"
        >
          {t("approval.approve")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide("N")}
          className="h-11 rounded-full border border-[#d7d0c4] px-6 text-sm font-semibold text-[#1c1915] disabled:text-[#8a8175]"
        >
          {t("approval.reject")}
        </button>
        {selected === null ? <span className="text-xs text-[#8a8175]">{t("approval.pick")}</span> : null}
      </div>
    </section>
  );
}
