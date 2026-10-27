"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { fetchGlossary, fetchVocabulary, type Vocabulary } from "@/lib/api";
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, parseLanguage, translate, type Language, type MessageKey } from "@/lib/i18n";

type Glossary = Record<string, { term: string; explanation: string }>;

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey, variables?: Record<string, string | number>) => string;
  glossary: Glossary;
  names: Vocabulary;
};

const NO_NAMES: Vocabulary = { models: {}, datasets: {}, metrics: {} };
const CHANGED = "axiomforge-language";
const LanguageContext = createContext<LanguageContextValue | null>(null);

let remembered: Language | null = null;

function readLanguage(): Language {
  try {
    return parseLanguage(window.localStorage.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return remembered ?? DEFAULT_LANGUAGE;
  }
}

function subscribe(listener: () => void): () => void {
  window.addEventListener("storage", listener);
  window.addEventListener(CHANGED, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(CHANGED, listener);
  };
}

export function LanguageProvider({ children, serverLanguage = DEFAULT_LANGUAGE, initialGlossary = {} }: { children: ReactNode; serverLanguage?: Language; initialGlossary?: Glossary }) {
  const language = useSyncExternalStore(subscribe, readLanguage, () => serverLanguage);
  const [glossary, setGlossary] = useState<Glossary>(initialGlossary);
  const [names, setNames] = useState<Vocabulary>(NO_NAMES);

  useEffect(() => {
    document.documentElement.lang = language;
    let cancelled = false;
    fetchGlossary(language)
      .then((terms) => {
        if (!cancelled) {
          setGlossary(terms);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGlossary({});
        }
      });
    fetchVocabulary(language)
      .then((loaded) => {
        if (!cancelled) {
          setNames(loaded);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNames(NO_NAMES);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    remembered = next;
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
    } catch {
      // the choice then lasts for this visit only
    }
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  const t = useCallback<LanguageContextValue["t"]>((key, variables) => translate(language, key, variables), [language]);
  const value = useMemo<LanguageContextValue>(() => ({ language, setLanguage, glossary, names, t }), [language, setLanguage, glossary, names, t]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const value = useContext(LanguageContext);
  if (!value) {
    throw new Error("useLanguage needs a LanguageProvider");
  }
  return value;
}
