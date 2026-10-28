"use client";

import Link from "next/link";
import { useLanguage } from "@/components/LanguageProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LANGUAGES } from "@/lib/i18n";

export function SiteHeader() {
  const { language, setLanguage, t } = useLanguage();
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 pt-6">
      <Link href="/" className="font-[family-name:var(--font-display)] text-lg font-semibold text-ink">
        {t("app.name")}
      </Link>
      <nav className="flex items-center gap-5 text-sm">
        <Link href="/" className="font-semibold text-accent">
          {t("nav.home")}
        </Link>
        <Link href="/campaigns" className="font-semibold text-accent">
          {t("nav.history")}
        </Link>
        <Link href="/research" className="font-semibold text-accent">
          {t("nav.research")}
        </Link>
        <div role="group" aria-label={t("nav.language")} className="flex overflow-hidden rounded-full border border-line bg-card text-xs font-semibold">
          {LANGUAGES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={language === item}
              onClick={() => setLanguage(item)}
              className={`px-3 py-1 uppercase ${language === item ? "bg-accent text-on-solid" : "text-muted hover:bg-page"}`}
            >
              {item}
            </button>
          ))}
        </div>
        <ThemeToggle />
      </nav>
    </header>
  );
}
