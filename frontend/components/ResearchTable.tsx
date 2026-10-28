"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { VerdictBadge } from "@/components/VerdictBadge";
import { formatSigned } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { claimText, formatP, statusTone, type SessionRow } from "@/lib/researchView";

export function ResearchTable({ rows }: { rows: SessionRow[] }) {
  const { language, names, t } = useLanguage();
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-2xl border border-line bg-card">
        <table className="w-full min-w-[56rem] text-left text-sm">
          <caption className="sr-only">{t("research.table.title")}</caption>
          <thead className="border-b border-line-soft text-xs text-muted">
            <tr>
              {(["claim", "stage", "exploration", "confirmation", "p", "adjusted", "status"] as const).map((column) => (
                <th key={column} scope="col" className="px-4 py-3 font-semibold">
                  {t(`research.table.${column}` as MessageKey)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ hypothesis, confirmation }) => (
              <tr key={hypothesis.id} className="border-b border-line-soft last:border-0">
                <th scope="row" className="px-4 py-3 font-semibold text-ink">
                  {claimText(hypothesis.subject, hypothesis.other, names.models)}
                </th>
                <td className="px-4 py-3 text-muted">{t(`research.stage.${hypothesis.stage}` as MessageKey) === `research.stage.${hypothesis.stage}` ? hypothesis.stage : t(`research.stage.${hypothesis.stage}` as MessageKey)}</td>
                <td className="px-4 py-3 text-muted">
                  {formatSigned(hypothesis.evidence.median_difference, language)} · {hypothesis.evidence.wins}/{hypothesis.evidence.datasets}
                </td>
                <td className="px-4 py-3 text-ink">
                  {confirmation ? (
                    <>
                      {formatSigned(confirmation.median_difference, language)} · {confirmation.wins}/{confirmation.datasets}
                    </>
                  ) : (
                    <span className="text-muted">{t("research.table.notRun")}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted">{formatP(confirmation?.p_value ?? null, language)}</td>
                <td className="px-4 py-3 text-ink">{formatP(confirmation?.adjusted_p_value ?? null, language)}</td>
                <td className="px-4 py-3">
                  {confirmation ? (
                    <VerdictBadge label={t(`research.confirmation.${confirmation.status}` as MessageKey)} tone={statusTone(confirmation.status)} />
                  ) : (
                    <span className="text-muted">–</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">{t("research.table.note")}</p>
    </div>
  );
}
