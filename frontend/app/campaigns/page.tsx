"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CampaignBadge } from "@/components/CampaignBadge";
import { fetchCampaigns, startDemoCampaign } from "@/lib/api";
import type { CampaignSummary } from "@/lib/types";

const POLL_MS = 3000;
const ACTIVE = new Set(["queued", "running"]);
const DEMO = "grinsztajn-2022";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const router = useRouter();

  const startDemo = async () => {
    if (!window.confirm("Run the ready campaign " + DEMO + "? It uses the sandbox for about five minutes and no language model.")) {
      return;
    }
    setStarting(true);
    try {
      router.push(`/campaign/${await startDemoCampaign(DEMO)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The campaign could not be started");
      setStarting(false);
    }
  };

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
      <button
        type="button"
        disabled={starting}
        onClick={() => void startDemo()}
        className="mt-6 h-11 cursor-pointer rounded-full bg-[#1f6b4a] px-5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#d5d0c6] disabled:text-[#6f675e]"
      >
        {starting ? "Starting" : `Run the ready campaign (${DEMO})`}
      </button>
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
