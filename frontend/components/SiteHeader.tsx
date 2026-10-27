"use client";

import Link from "next/link";
import { useLanguage } from "@/components/LanguageProvider";
import { LANGUAGES } from "@/lib/i18n";

export function SiteHeader() {
  const { language, setLanguage, t } = useLanguage();
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 pt-6">
      <Link href="/" className="font-[family-name:var(--font-display)] text-lg font-semibold text-[#1c1915]">
        {t("app.name")}
      </Link>
      <nav className="flex items-center gap-5 text-sm">
        <Link href="/" className="font-semibold text-[#1f6b4a]">
          {t("nav.home")}
        </Link>
        <Link href="/campaigns" className="font-semibold text-[#1f6b4a]">
          {t("nav.history")}
        </Link>
        <div role="group" aria-label={t("nav.language")} className="flex overflow-hidden rounded-full border border-[#d7d0c4] bg-white text-xs font-semibold">
          {LANGUAGES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={language === item}
              onClick={() => setLanguage(item)}
              className={`px-3 py-1 uppercase ${language === item ? "bg-[#1f6b4a] text-white" : "text-[#5c564e] hover:bg-[#f4f0e6]"}`}
            >
              {item}
            </button>
          ))}
        </div>
      </nav>
    </header>
  );
}
