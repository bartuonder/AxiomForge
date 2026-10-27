"use client";

import { useLanguage } from "@/components/LanguageProvider";
import type { MessageKey } from "@/lib/i18n";
import type { ResearchStep } from "@/lib/types";

type AgentTimelineProps = {
  steps: ResearchStep[];
};

export function AgentTimeline({ steps }: AgentTimelineProps) {
  const { t } = useLanguage();
  return (
    <ol className="mx-auto flex w-full max-w-3xl flex-col gap-0">
      {steps.map((step, index) => {
        const key = `step.${step.id}` as MessageKey;
        const label = t(key) === key ? step.id : t(key);
        const isLast = index === steps.length - 1;
        return (
          <li key={step.id} className="grid grid-cols-[28px_1fr] gap-4">
            <div className="flex flex-col items-center">
              <span
                className={`mt-1 h-3.5 w-3.5 rounded-full border-2 ${
                  step.phase === "done"
                    ? "border-accent bg-accent"
                    : step.phase === "active"
                      ? "border-accent bg-card shadow-[0_0_0_4px_rgba(31,107,74,0.15)]"
                      : "border-line bg-card"
                }`}
              />
              {isLast ? null : <span className={`my-1 w-px flex-1 ${step.phase === "done" ? "bg-accent" : "bg-line-soft"}`} />}
            </div>
            <div className={`pb-6 ${isLast ? "pb-0" : ""}`}>
              <p className={`text-lg ${step.phase === "pending" ? "text-faint" : "text-ink"}`}>{label}</p>
              <p className="text-sm text-muted">
                {step.phase === "done" ? t("progress.done") : step.phase === "active" ? t("progress.active") : t("progress.waiting")}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
