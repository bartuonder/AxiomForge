"use client";

import type { ResearchMode } from "@/lib/types";

type ResearchFormProps = {
  query: string;
  mode: ResearchMode;
  busy: boolean;
  onQueryChange: (value: string) => void;
  onModeChange: (value: ResearchMode) => void;
  onSubmit: () => void;
};

const MODES: { value: ResearchMode; label: string; hint: string }[] = [
  { value: "experiment", label: "Experiment", hint: "One dataset, two or more models named in the question." },
  {
    value: "campaign",
    label: "Campaign",
    hint: "Replicate a claim across many datasets. Uses the sandbox for several minutes after you approve a plan.",
  },
];

export function ResearchForm({ query, mode, busy, onQueryChange, onModeChange, onSubmit }: ResearchFormProps) {
  const hint = MODES.find((item) => item.value === mode)?.hint ?? "";
  return (
    <form
      className="flex w-full flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <fieldset className="flex flex-wrap items-center gap-4" disabled={busy}>
        <legend className="sr-only">Mode</legend>
        {MODES.map((item) => (
          <label key={item.value} className="flex cursor-pointer items-center gap-2 text-sm text-[#1c1915]">
            <input
              type="radio"
              name="mode"
              value={item.value}
              checked={mode === item.value}
              onChange={() => onModeChange(item.value)}
              className="h-4 w-4 accent-[#1f6b4a]"
            />
            {item.label}
          </label>
        ))}
        <span className="text-xs text-[#5c564e]">{hint}</span>
      </fieldset>
      <div className="flex w-full flex-col gap-3 sm:flex-row">
        <label className="sr-only" htmlFor="research-query">
          Research topic
        </label>
        <input
          id="research-query"
          value={query}
          disabled={busy}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={mode === "campaign" ? "Which claim should be replicated?" : "What should the agents study?"}
          className="h-12 flex-1 rounded-full border border-[#d7d0c4] bg-white px-5 text-[15px] text-[#1c1915] outline-none placeholder:text-[#a3988c] focus:border-[#1f6b4a] disabled:bg-[#f7f4ee]"
        />
        <button
          type="submit"
          disabled={busy || query.trim().length === 0}
          className="h-12 cursor-pointer rounded-full bg-[#1f6b4a] px-6 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#d5d0c6] disabled:text-[#6f675e]"
        >
          {busy ? "Running" : mode === "campaign" ? "Start Campaign" : "Start Research"}
        </button>
      </div>
    </form>
  );
}
