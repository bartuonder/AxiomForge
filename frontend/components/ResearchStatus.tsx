import type { ResearchSnapshot } from "@/lib/types";

type Tone = "good" | "warn" | "bad" | "wait";

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

function verificationRow(snapshot: ResearchSnapshot): StatusRow {
  if (snapshot.verification_status === "Passed") {
    return { key: "verification", tone: "good", title: "Verification passed" };
  }
  if (snapshot.verification_status === "Failed") {
    return {
      key: "verification",
      tone: "bad",
      title: "Verification failed",
      detail: snapshot.verifier_feedback,
    };
  }
  return { key: "verification", tone: "wait", title: "Verification pending" };
}

function stabilityRow(snapshot: ResearchSnapshot): StatusRow | null {
  const { instability } = snapshot;
  if (!snapshot.verification_status || !instability.unstable) {
    return null;
  }
  const flagged = instability.flagged
    .map((item) => `${item.model} ${item.metric} std ${item.std.toFixed(3)}`)
    .join("; ");
  return {
    key: "stability",
    tone: "warn",
    title: `High variance across splits (threshold ${instability.std_threshold})`,
    detail: flagged,
  };
}

function claimsRow(snapshot: ResearchSnapshot): StatusRow {
  if (snapshot.research_status === "Completed") {
    return { key: "claims", tone: "good", title: "Claims match the results" };
  }
  if (snapshot.research_status === "NeedsReview") {
    return {
      key: "claims",
      tone: "warn",
      title: "Needs review: the claim check still found problems after two rewrites",
      detail: snapshot.consistency_feedback,
    };
  }
  return { key: "claims", tone: "wait", title: "Claim check pending" };
}

function campaignRow(snapshot: ResearchSnapshot): StatusRow {
  const detail = snapshot.campaign_mlflow_run_id ? `MLflow run ${snapshot.campaign_mlflow_run_id}` : undefined;
  if (snapshot.campaign_status === "completed") {
    return { key: "campaign", tone: "good", title: "Campaign finished and its report passed the traceability check", detail };
  }
  if (snapshot.campaign_status === "needs_review") {
    return { key: "campaign", tone: "warn", title: "Campaign finished, but its own report check found problems", detail };
  }
  if (snapshot.campaign_status) {
    return { key: "campaign", tone: "wait", title: `Campaign ${snapshot.campaign_status}` };
  }
  return { key: "campaign", tone: "wait", title: "Campaign not collected yet" };
}

function metaClaimsRow(snapshot: ResearchSnapshot): StatusRow {
  if (snapshot.research_status === "Completed") {
    return { key: "claims", tone: "good", title: "The report matches the campaign evidence" };
  }
  if (snapshot.research_status === "NeedsReview") {
    return {
      key: "claims",
      tone: "warn",
      title: "Needs review: the report check still found problems after two rewrites",
      detail: snapshot.consistency_feedback,
    };
  }
  return { key: "claims", tone: "wait", title: "Report check pending" };
}

export function ResearchStatus({ snapshot }: ResearchStatusProps) {
  const stability = stabilityRow(snapshot);
  const rows =
    snapshot.mode === "campaign"
      ? [campaignRow(snapshot), metaClaimsRow(snapshot)]
      : [verificationRow(snapshot), ...(stability ? [stability] : []), claimsRow(snapshot)];
  const notes = snapshot.referee_notes ?? [];
  return (
    <>
      <ul aria-label="Research checks" className="mt-6 space-y-2">
        {rows.map((row) => (
          <li
            key={row.key}
            className={`flex gap-3 rounded border px-4 py-3 text-sm ${TONE_STYLES[row.tone].box}`}
          >
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
          <summary className="cursor-pointer font-semibold">
            Referee notes ({notes.length}), advisory: they did not decide the status
          </summary>
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
