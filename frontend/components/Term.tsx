"use client";

import type { ReactNode } from "react";
import { useLanguage } from "@/components/LanguageProvider";

type TermProps = {
  id: string;
  children: ReactNode;
};

export function Term({ id, children }: TermProps) {
  const { glossary } = useLanguage();
  const entry = glossary[id];
  if (!entry) {
    return <>{children}</>;
  }
  return (
    <span className="group relative inline-block">
      <button
        type="button"
        aria-label={`${entry.term}: ${entry.explanation}`}
        className="cursor-help border-b border-dotted border-faint text-inherit"
      >
        {children}
      </button>
      <span
        role="tooltip"
        className="invisible absolute bottom-full left-0 z-20 mb-2 w-64 rounded-xl border border-line bg-card p-3 text-left text-xs leading-5 font-normal text-ink shadow-lg group-focus-within:visible group-hover:visible"
      >
        <span className="block font-semibold text-accent">{entry.term}</span>
        {entry.explanation}
      </span>
    </span>
  );
}
