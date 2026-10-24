import {
  API_URL,
  type CampaignReport,
  type CampaignState,
  type CampaignSummary,
  type ResearchMode,
  type ResearchSnapshot,
} from "@/lib/types";

export async function startResearch(query: string, mode: ResearchMode): Promise<{ thread_id: string }> {
  const response = await fetch(`${API_URL}/start_research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchResearch(threadId: string): Promise<ResearchSnapshot> {
  const response = await fetch(`${API_URL}/research/${threadId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function approvePlan(
  threadId: string,
  decision: "Y" | "N",
  selected?: number,
): Promise<void> {
  const response = await fetch(`${API_URL}/approve_plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, decision, selected }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function fetchReport(threadId: string): Promise<string> {
  const response = await fetch(`${API_URL}/reports/${threadId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = (await response.json()) as { markdown: string };
  return body.markdown;
}

export async function fetchCampaigns(): Promise<CampaignSummary[]> {
  const response = await fetch(`${API_URL}/campaigns`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = (await response.json()) as { items: CampaignSummary[] };
  return body.items;
}

export async function fetchCampaign(campaignId: string): Promise<CampaignState> {
  const response = await fetch(`${API_URL}/campaign/${encodeURIComponent(campaignId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchCampaignReport(campaignId: string): Promise<CampaignReport> {
  const response = await fetch(`${API_URL}/campaign/${encodeURIComponent(campaignId)}/report`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || response.statusText;
  } catch {
    return response.statusText;
  }
}
