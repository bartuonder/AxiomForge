"use client";

import { useState } from "react";
import type { ExperimentSpec } from "@/lib/types";

type ApprovalDialogProps = {
  hypotheses: string[];
  specs: ExperimentSpec[];
  busy: boolean;
  onDecide: (decision: "Y" | "N", selected?: number) => void;
};

function describeParams(spec: ExperimentSpec | undefined): string {
  if (!spec) {
    return "";
  }
  const pairs = Object.entries(spec.params).flatMap(([model, values]) =>
    Object.entries(values).map(([name, value]) => `${model}.${name} = ${String(value)}`),
  );
  return pairs.length ? pairs.join(", ") : "default parameters";
}

export function ApprovalDialog({ hypotheses, specs, busy, onDecide }: ApprovalDialogProps) {
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <section className="mx-auto w-full max-w-3xl rounded-3xl border border-[#d7d0c4] bg-white p-6 shadow-[0_20px_60px_rgba(28,25,21,0.08)]">
      <p className="text-xs font-semibold tracking-[0.16em] text-[#1f6b4a] uppercase">
        Plan paused
      </p>
      <h2 className="mt-2 text-2xl text-[#1c1915]">Choose the hypothesis to run</h2>
      <p className="mt-2 text-sm text-[#5c564e]">Only the hypothesis you pick is tested.</p>
      <fieldset className="mt-5 space-y-3" disabled={busy}>
        <legend className="sr-only">Hypotheses</legend>
        {hypotheses.map((item, index) => {
          const spec = specs[index];
          const checked = selected === index;
          return (
            <label
              key={item}
              className={`flex cursor-pointer gap-3 rounded-2xl border px-4 py-3 text-sm leading-6 text-[#1c1915] ${
                checked ? "border-[#1f6b4a] bg-[#eef6f1]" : "border-transparent bg-[#f6f1e8]"
              }`}
            >
              <input
                type="radio"
                name="hypothesis"
                value={index}
                checked={checked}
                onChange={() => setSelected(index)}
                className="mt-1.5 h-4 w-4 shrink-0 accent-[#1f6b4a]"
              />
              <span>
                <span className="mr-2 font-semibold text-[#1f6b4a]">{index + 1}.</span>
                {item}
                {spec ? (
                  <span className="mt-1 block text-xs text-[#5c564e]">
                    Dataset: {spec.dataset} · {describeParams(spec)}
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
