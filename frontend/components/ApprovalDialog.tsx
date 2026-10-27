"use client";

import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import type { ExperimentSpec } from "@/lib/types";

type ApprovalDialogProps = {
  hypotheses: string[];
  specs: ExperimentSpec[];
  busy: boolean;
  onDecide: (decision: "Y" | "N", selected?: number) => void;
};

function describeParams(spec: ExperimentSpec | undefined, fallback: string): string {
  if (!spec) {
    return "";
  }
  const pairs = Object.entries(spec.params).flatMap(([model, values]) =>
    Object.entries(values).map(([name, value]) => `${model}.${name} = ${String(value)}`),
  );
  return pairs.length ? pairs.join(", ") : fallback;
}

export function ApprovalDialog({ hypotheses, specs, busy, onDecide }: ApprovalDialogProps) {
  const { t } = useLanguage();
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <section className="mx-auto w-full max-w-3xl rounded-3xl border border-line bg-card p-6 shadow-[0_20px_60px_rgba(28,25,21,0.08)]">
      <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
        {t("approval.exp.kicker")}
      </p>
      <h2 className="mt-2 text-2xl text-ink">{t("approval.exp.title")}</h2>
      <p className="mt-2 text-sm text-muted">{t("approval.exp.hint")}</p>
      <fieldset className="mt-5 space-y-3" disabled={busy}>
        <legend className="sr-only">{t("approval.exp.legend")}</legend>
        {hypotheses.map((item, index) => {
          const spec = specs[index];
          const checked = selected === index;
          return (
            <label
              key={item}
              className={`flex cursor-pointer gap-3 rounded-2xl border px-4 py-3 text-sm leading-6 text-ink ${
                checked ? "border-accent bg-accent-tint" : "border-transparent bg-panel2"
              }`}
            >
              <input
                type="radio"
                name="hypothesis"
                value={index}
                checked={checked}
                onChange={() => setSelected(index)}
                className="mt-1.5 h-4 w-4 shrink-0 accent-accent"
              />
              <span>
                <span className="mr-2 font-semibold text-accent">{index + 1}.</span>
                {item}
                {spec ? (
                  <span className="mt-1 block text-xs text-muted">
                    {t("approval.exp.dataset", { dataset: spec.dataset })} · {describeParams(spec, t("approval.exp.defaults"))}
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
          className="h-11 rounded-full bg-accent px-5 text-sm font-semibold text-on-solid disabled:bg-accent-dim"
        >
          {t("approval.exp.yes")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide("N")}
          className="h-11 rounded-full border border-line px-5 text-sm font-semibold text-ink disabled:text-faint"
        >
          {t("approval.exp.no")}
        </button>
      </div>
    </section>
  );
}
