"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CampaignBadge } from "@/components/CampaignBadge";
import { fetchCampaigns } from "@/lib/api";
import type { CampaignSummary } from "@/lib/types";

const POLL_MS = 3000;
const ACTIVE = new Set(["queued", "running"]);

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let active = true;
      try {
        const items = await fetchCampaigns();
        if (cancelled) {
          return;
        }
        setCampaigns(items);
        setError("");
        active = items.some((item) => ACTIVE.has(item.status));
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Campaign list request failed");
        }
      }
      if (!cancelled && active) {
        timer = window.setTimeout(() => void tick(), POLL_MS);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-16">
      <Link href="/" className="text-sm font-semibold text-[#1f6b4a]">
        Back to console
      </Link>
      <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-[#8a8175] uppercase">Replication</p>
      <h1 className="mt-2 text-4xl text-[#1c1915]">Campaigns</h1>
      {error ? <p className="mt-8 text-sm text-[#9b3d2b]">{error}</p> : null}
      {campaigns && campaigns.length === 0 ? (
        <p className="mt-8 text-sm text-[#5c564e]">
          No campaign yet. Start one with <code>POST /start_campaign</code> or{" "}
          <code>python -m app.campaign run --demo grinsztajn-2022</code>.
        </p>
      ) : null}
      <ul className="mt-10 space-y-4">
        {(campaigns ?? []).map((campaign) => (
          <li key={campaign.id}>
            <Link
              href={`/campaign/${campaign.id}`}
              className="block rounded-xl border border-[#d7d0c4] bg-white p-5 hover:border-[#1f6b4a]"
            >
              <div className="flex items-start justify-between gap-4">
                <p className="text-lg text-[#1c1915]">{campaign.title || campaign.id}</p>
                <CampaignBadge status={campaign.status} />
              </div>
              <p className="mt-2 text-sm text-[#5c564e]">
                {campaign.finished} of {campaign.datasets} datasets finished
                {campaign.failed ? `, ${campaign.failed} failed` : ""}
              </p>
              {campaign.verdicts.length ? (
                <p className="mt-2 text-sm text-[#14472f]">
                  {campaign.verdicts.map((item) => `${item.id} ${item.verdict.replace("_", " ")}`).join(" · ")}
                </p>
              ) : null}
              <p className="mt-2 text-xs text-[#8a8175]">{campaign.id}</p>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
