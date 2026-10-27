"use client";

import { useLanguage } from "@/components/LanguageProvider";
import type { ErrorInfo } from "@/lib/types";

type ErrorNoticeProps = {
  info?: ErrorInfo | null;
  fallback?: string;
};

export function ErrorNotice({ info, fallback }: ErrorNoticeProps) {
  const { t } = useLanguage();
  if (!info && !fallback) {
    return null;
  }
  return (
    <section role="alert" className="mx-auto w-full max-w-3xl space-y-3 rounded-2xl border border-[#d9a99e] bg-[#faeeea] p-5 text-[#6e2a1c]">
      <h2 className="text-lg font-semibold">{info ? info.title : t("error.title")}</h2>
      {info ? (
        <>
          <p className="text-sm">{info.message}</p>
          <p className="text-sm">
            <span className="font-semibold">{t("error.hint")}</span> {info.hint}
          </p>
          {info.technical ? (
            <details className="text-xs">
              <summary className="cursor-pointer font-semibold">{t("error.technical")}</summary>
              <p className="mt-2 break-words font-mono">{info.technical}</p>
            </details>
          ) : null}
        </>
      ) : (
        <p className="text-sm">{fallback}</p>
      )}
    </section>
  );
}
