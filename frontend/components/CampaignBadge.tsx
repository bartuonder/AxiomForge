"use client";

import { useLanguage } from "@/components/LanguageProvider";
import type { MessageKey } from "@/lib/i18n";
import type { CampaignStatus } from "@/lib/types";

const STYLES: Record<CampaignStatus, string> = {
  queued: "border-line bg-card text-muted",
  running: "border-warn bg-warn-tint text-warn-ink",
  completed: "border-accent-line bg-accent-tint text-accent-ink",
  needs_review: "border-warn bg-warn-tint text-warn-ink",
  failed: "border-danger-line bg-danger-tint text-danger-ink",
  cancelled: "border-line bg-stopped-tint text-muted",
};

type CampaignBadgeProps = {
  status: CampaignStatus;
};

export function CampaignBadge({ status }: CampaignBadgeProps) {
  const { t } = useLanguage();
  const known = status in STYLES;
  return (
    <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${known ? STYLES[status] : STYLES.queued}`}>
      {known ? t(`status.${status}` as MessageKey) : status}
    </span>
  );
}
