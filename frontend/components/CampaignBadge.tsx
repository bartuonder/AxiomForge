"use client";

import { useLanguage } from "@/components/LanguageProvider";
import type { MessageKey } from "@/lib/i18n";
import type { CampaignStatus } from "@/lib/types";

const STYLES: Record<CampaignStatus, string> = {
  queued: "border-[#d7d0c4] bg-white text-[#5c564e]",
  running: "border-[#c9a227] bg-[#fbf3d6] text-[#5c4a0c]",
  completed: "border-[#b9d8c7] bg-[#eef6f1] text-[#14472f]",
  needs_review: "border-[#c9a227] bg-[#fbf3d6] text-[#5c4a0c]",
  failed: "border-[#d9a99e] bg-[#faeeea] text-[#6e2a1c]",
  cancelled: "border-[#d7d0c4] bg-[#f3efe7] text-[#5c564e]",
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
