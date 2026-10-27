"use client";

import { useSyncExternalStore } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { otherTheme, parseTheme, resolveTheme, THEME_CHANGED, THEME_STORAGE_KEY, type Theme } from "@/lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function readTheme(): Theme {
  let stored: Theme | null = null;
  try {
    stored = parseTheme(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    stored = parseTheme(document.documentElement.dataset.theme);
  }
  return resolveTheme(stored, window.matchMedia(DARK_QUERY).matches);
}

function subscribe(listener: () => void): () => void {
  const media = window.matchMedia(DARK_QUERY);
  window.addEventListener("storage", listener);
  window.addEventListener(THEME_CHANGED, listener);
  media.addEventListener("change", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(THEME_CHANGED, listener);
    media.removeEventListener("change", listener);
  };
}

function choose(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // the choice then lasts for this visit only
  }
  window.dispatchEvent(new Event(THEME_CHANGED));
}

export function ThemeToggle({ serverTheme = "light" }: { serverTheme?: Theme }) {
  const { t } = useLanguage();
  const theme = useSyncExternalStore(subscribe, readTheme, () => serverTheme);
  const next = otherTheme(theme);
  return (
    <button
      type="button"
      onClick={() => choose(next)}
      aria-label={t(next === "dark" ? "theme.toDark" : "theme.toLight")}
      title={t(next === "dark" ? "theme.toDark" : "theme.toLight")}
      className="h-8 w-8 rounded-full border border-line bg-card text-sm text-muted hover:bg-page"
    >
      <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
