"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { startResearchSession } from "@/lib/api";
import { friendlyApiError } from "@/lib/apiErrors";
import type { MessageKey } from "@/lib/i18n";
import { canStart, DEFAULT_RESEARCH_MODELS, RESEARCH_MODELS, startPayload, toggleModel, TUNING_ITERATIONS, type StartChoices } from "@/lib/researchView";

const GENERATORS: { value: StartChoices["generator"]; label: MessageKey }[] = [
  { value: "rules", label: "research.start.generator.rules" },
  { value: "llm", label: "research.start.generator.llm" },
];

type StartFormProps = {
  choices: StartChoices;
  busy: boolean;
  error: string;
  onChange: (choices: StartChoices) => void;
  onSubmit: () => void;
};

export function StartForm({ choices, busy, error, onChange, onSubmit }: StartFormProps) {
  const { names, t } = useLanguage();
  const ready = canStart(choices);
  return (
    <form
      className="mt-8 space-y-5 rounded-2xl border border-line bg-card p-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="space-y-1">
        <h2 className="text-xl text-ink">{t("research.start.title")}</h2>
        <p className="text-sm leading-6 text-muted">{t("research.start.subtitle")}</p>
      </div>
      <fieldset className="space-y-2" disabled={busy}>
        <legend className="text-sm font-semibold text-ink">{t("research.start.models")}</legend>
        <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          {RESEARCH_MODELS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={choices.models.includes(key)} onChange={() => onChange({ ...choices, models: toggleModel(choices.models, key) })} />
              {names.models[key] ?? key}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={choices.tuned} disabled={busy} onChange={() => onChange({ ...choices, tuned: !choices.tuned })} />
          {t("research.start.tuned", { iterations: TUNING_ITERATIONS })}
        </label>
        <p className="pl-6 text-xs text-muted">{t("research.start.tunedHint")}</p>
      </div>
      <fieldset className="space-y-1" disabled={busy}>
        <legend className="text-sm font-semibold text-ink">{t("research.start.generator")}</legend>
        {GENERATORS.map((item) => (
          <label key={item.value} className="flex items-center gap-2 text-sm text-ink">
            <input type="radio" name="generator" checked={choices.generator === item.value} onChange={() => onChange({ ...choices, generator: item.value })} />
            {t(item.label)}
          </label>
        ))}
      </fieldset>
      <p className="text-xs leading-5 text-muted">{t("research.start.cost")}</p>
      {!ready ? <p className="text-sm text-muted">{t("research.start.needTwo")}</p> : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={busy || !ready}
        className="rounded-full border border-accent bg-accent px-5 py-2 text-sm font-semibold text-on-solid hover:opacity-90 disabled:opacity-50"
      >
        {busy ? t("research.start.busy") : t("research.start.button")}
      </button>
    </form>
  );
}

export function StartSession() {
  const { t } = useLanguage();
  const router = useRouter();
  const [choices, setChoices] = useState<StartChoices>({ models: DEFAULT_RESEARCH_MODELS, tuned: false, generator: "rules" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const started = await startResearchSession(startPayload(choices));
      router.push(`/research/${encodeURIComponent(started.session_id)}`);
    } catch (caught) {
      setError(friendlyApiError(caught instanceof Error ? caught.message : "", t) || t("error.request"));
      setBusy(false);
    }
  };

  return <StartForm choices={choices} busy={busy} error={error} onChange={setChoices} onSubmit={() => void submit()} />;
}
