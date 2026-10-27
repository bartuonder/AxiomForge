"use client";

import { useLanguage } from "@/components/LanguageProvider";
import type { MessageKey } from "@/lib/i18n";
import type { ResearchSnapshot } from "@/lib/types";

type Tone = "good" | "warn" | "bad" | "wait";
type Translate = (key: MessageKey, variables?: Record<string, string | number>) => string;

type StatusRow = {
  key: string;
  tone: Tone;
  title: string;
  detail?: string;
};

type ResearchStatusProps = {
  snapshot: ResearchSnapshot;
};

const TONE_STYLES: Record<Tone, { box: string; dot: string }> = {
  good: { box: "border-accent-line bg-accent-tint text-accent-ink", dot: "bg-accent" },
  warn: { box: "border-warn bg-warn-tint text-warn-ink", dot: "bg-warn" },
  bad: { box: "border-danger-line bg-danger-tint text-danger-ink", dot: "bg-danger" },
  wait: { box: "border-line bg-card text-muted", dot: "bg-line" },
};

function verificationRow(snapshot: ResearchSnapshot, t: Translate): StatusRow {
  if (snapshot.verification_status === "Passed") {
    return { key: "verification", tone: "good", title: t("check.verification.passed") };
  }
  if (snapshot.verification_status === "Failed") {
    return { key: "verification", tone: "bad", title: t("check.verification.failed"), detail: snapshot.verifier_feedback };
  }
  return { key: "verification", tone: "wait", title: t("check.verification.pending") };
}

function stabilityRow(snapshot: ResearchSnapshot, t: Translate): StatusRow | null {
  const { instability } = snapshot;
  if (!snapshot.verification_status || !instability.unstable) {
    return null;
  }
  const flagged = instability.flagged.map((item) => `${item.model} ${item.metric} std ${item.std.toFixed(3)}`).join("; ");
  return { key: "stability", tone: "warn", title: t("check.variance", { threshold: instability.std_threshold }), detail: flagged };
}

function claimsRow(snapshot: ResearchSnapshot, t: Translate): StatusRow {
  if (snapshot.research_status === "Completed") {
    return { key: "claims", tone: "good", title: t("check.claims.ok") };
  }
  if (snapshot.research_status === "NeedsReview") {
    return { key: "claims", tone: "warn", title: t("check.claims.review"), detail: snapshot.consistency_feedback };
  }
  return { key: "claims", tone: "wait", title: t("check.claims.pending") };
}

function campaignRow(snapshot: ResearchSnapshot, t: Translate): StatusRow {
  const detail = snapshot.campaign_mlflow_run_id ? t("check.mlflow", { id: snapshot.campaign_mlflow_run_id }) : undefined;
  if (snapshot.campaign_status === "completed") {
    return { key: "campaign", tone: "good", title: t("check.campaign.ok"), detail };
  }
  if (snapshot.campaign_status === "needs_review") {
    return { key: "campaign", tone: "warn", title: t("check.campaign.review"), detail };
  }
  if (snapshot.campaign_status) {
    const known = `status.${snapshot.campaign_status}` as MessageKey;
    const label = t(known) === known ? snapshot.campaign_status : t(known);
    return { key: "campaign", tone: "wait", title: t("check.campaign.state", { status: label }) };
  }
  return { key: "campaign", tone: "wait", title: t("check.campaign.none") };
}

function metaClaimsRow(snapshot: ResearchSnapshot, t: Translate): StatusRow {
  if (snapshot.research_status === "Completed") {
    return { key: "claims", tone: "good", title: t("check.meta.ok") };
  }
  if (snapshot.research_status === "NeedsReview") {
    return { key: "claims", tone: "warn", title: t("check.meta.review"), detail: snapshot.consistency_feedback };
  }
  return { key: "claims", tone: "wait", title: t("check.meta.pending") };
}

export function ResearchStatus({ snapshot }: ResearchStatusProps) {
  const { t } = useLanguage();
  const stability = stabilityRow(snapshot, t);
  const rows =
    snapshot.mode === "campaign"
      ? [campaignRow(snapshot, t), metaClaimsRow(snapshot, t)]
      : [verificationRow(snapshot, t), ...(stability ? [stability] : []), claimsRow(snapshot, t)];
  const notes = snapshot.referee_notes ?? [];
  return (
    <>
      <ul aria-label={t("check.title")} className="mt-6 space-y-2">
        {rows.map((row) => (
          <li key={row.key} className={`flex gap-3 rounded border px-4 py-3 text-sm ${TONE_STYLES[row.tone].box}`}>
            <span aria-hidden className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${TONE_STYLES[row.tone].dot}`} />
            <div>
              <p className="font-semibold">{row.title}</p>
              {row.detail ? <p className="mt-1 leading-6">{row.detail}</p> : null}
            </div>
          </li>
        ))}
      </ul>
      {notes.length > 0 ? (
        <details className="mt-3 rounded border border-line bg-card px-4 py-3 text-sm text-muted">
          <summary className="cursor-pointer font-semibold">{t("check.notes", { count: notes.length })}</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 leading-6">
            {notes.map((note, index) => (
              <li key={`${index}-${note.slice(0, 24)}`}>{note}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}
