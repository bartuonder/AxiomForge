"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { arxivReferences } from "@/lib/campaignView";
import type { MessageKey } from "@/lib/i18n";
import type { ResearchMode } from "@/lib/types";

type ResearchFormProps = {
  query: string;
  mode: ResearchMode;
  busy: boolean;
  onQueryChange: (value: string) => void;
  onModeChange: (value: ResearchMode) => void;
  onSubmit: () => void;
};

const MODES: { value: ResearchMode; label: MessageKey; hint: MessageKey }[] = [
  { value: "campaign", label: "form.mode.campaign", hint: "form.mode.campaign.hint" },
  { value: "experiment", label: "form.mode.experiment", hint: "form.mode.experiment.hint" },
];

const EXAMPLES: { label: MessageKey; query: MessageKey }[] = [
  { label: "example.trees.label", query: "example.trees.query" },
  { label: "example.paper.label", query: "example.paper.query" },
  { label: "example.boost.label", query: "example.boost.query" },
];

export function ResearchForm({ query, mode, busy, onQueryChange, onModeChange, onSubmit }: ResearchFormProps) {
  const { t } = useLanguage();
  const papers = arxivReferences(query);
  return (
    <form
      className="mx-auto flex w-full max-w-3xl flex-col gap-5 rounded-3xl border border-[#d7d0c4] bg-white p-6 shadow-[0_20px_60px_rgba(28,25,21,0.06)]"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="space-y-2">
        <label className="text-sm font-semibold text-[#1c1915]" htmlFor="research-query">
          {t("form.label")}
        </label>
        <textarea
          id="research-query"
          value={query}
          rows={2}
          disabled={busy}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={mode === "campaign" ? t("form.placeholder.campaign") : t("form.placeholder.experiment")}
          className="w-full resize-none rounded-2xl border border-[#d7d0c4] bg-[#fbf9f4] px-4 py-3 text-[15px] leading-6 text-[#1c1915] outline-none placeholder:text-[#a3988c] focus:border-[#1f6b4a] disabled:bg-[#f7f4ee]"
        />
        {papers.length > 0 ? (
          <p className="text-xs text-[#14472f]">{t(mode === "campaign" ? "form.arxiv" : "form.arxivIgnored", { ids: papers.join(", ") })}</p>
        ) : null}
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold tracking-[0.12em] text-[#8a8175] uppercase">{t("form.examples")}</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example.query}
              type="button"
              disabled={busy}
              onClick={() => onQueryChange(t(example.query))}
              className="rounded-full border border-[#d7d0c4] bg-[#fbf9f4] px-4 py-1.5 text-left text-sm text-[#1c1915] hover:border-[#1f6b4a] disabled:text-[#a3988c]"
            >
              {t(example.label)}
            </button>
          ))}
        </div>
      </div>

      <fieldset className="grid gap-3 sm:grid-cols-2" disabled={busy}>
        <legend className="sr-only">Mode</legend>
        {MODES.map((item) => (
          <label
            key={item.value}
            className={`flex cursor-pointer gap-3 rounded-2xl border p-4 text-sm ${mode === item.value ? "border-[#1f6b4a] bg-[#eef6f1]" : "border-[#e4ddd2] bg-white"}`}
          >
            <input type="radio" name="mode" value={item.value} checked={mode === item.value} onChange={() => onModeChange(item.value)} className="mt-1 h-4 w-4 accent-[#1f6b4a]" />
            <span>
              <span className="block font-semibold text-[#1c1915]">{t(item.label)}</span>
              <span className="mt-1 block text-xs leading-5 text-[#5c564e]">{t(item.hint)}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-[#8a8175]">{t("form.cost")}</p>
        <button
          type="submit"
          disabled={busy || query.trim().length === 0}
          className="h-12 shrink-0 cursor-pointer rounded-full bg-[#1f6b4a] px-7 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#d5d0c6] disabled:text-[#6f675e]"
        >
          {busy ? t("form.running") : t("form.start")}
        </button>
      </div>
    </form>
  );
}
