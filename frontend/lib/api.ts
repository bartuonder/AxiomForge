import {
  API_URL,
  type CampaignReport,
  type PlainSummary,
  type CampaignState,
  type CampaignSummary,
  type ResearchMode,
  type ResearchSnapshot,
  type SessionDetail,
  type SessionSummary,
} from "@/lib/types";
import type { StartPayload } from "@/lib/researchView";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

function postHeaders(): Record<string, string> {
  return API_KEY ? { "Content-Type": "application/json", "X-API-Key": API_KEY } : { "Content-Type": "application/json" };
}

export async function startResearch(query: string, mode: ResearchMode): Promise<{ thread_id: string }> {
  const response = await fetch(`${API_URL}/start_research`, {
    method: "POST",
    headers: postHeaders(),
    body: JSON.stringify({ query, mode }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchResearch(threadId: string, language: string = "tr"): Promise<ResearchSnapshot> {
  const response = await fetch(`${API_URL}/research/${threadId}?lang=${language}`, { cache: "no-store" });
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
    headers: postHeaders(),
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

export async function startDemoCampaign(demo: string): Promise<string> {
  const response = await fetch(`${API_URL}/start_campaign`, {
    method: "POST",
    headers: postHeaders(),
    body: JSON.stringify({ demo }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = (await response.json()) as { campaign_id: string };
  return body.campaign_id;
}

export async function cancelCampaign(campaignId: string): Promise<void> {
  const response = await fetch(`${API_URL}/campaign/${encodeURIComponent(campaignId)}/cancel`, { method: "POST", headers: postHeaders() });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function retryCampaign(campaignId: string): Promise<void> {
  const response = await fetch(`${API_URL}/campaign/${encodeURIComponent(campaignId)}/retry`, { method: "POST", headers: postHeaders() });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function retryResearch(threadId: string): Promise<void> {
  const response = await fetch(`${API_URL}/research/${encodeURIComponent(threadId)}/retry`, { method: "POST", headers: postHeaders() });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function startResearchSession(payload: StartPayload): Promise<{ session_id: string }> {
  const response = await fetch(`${API_URL}/start_research_session`, { method: "POST", headers: postHeaders(), body: JSON.stringify(payload) });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function cancelResearchSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_URL}/research_sessions/${encodeURIComponent(sessionId)}/cancel`, { method: "POST", headers: postHeaders() });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function retryResearchSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_URL}/research_sessions/${encodeURIComponent(sessionId)}/retry`, { method: "POST", headers: postHeaders() });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function fetchResearchSessions(): Promise<SessionSummary[]> {
  const response = await fetch(`${API_URL}/research_sessions`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return ((await response.json()) as { items: SessionSummary[] }).items;
}

export async function fetchResearchSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`${API_URL}/research_sessions/${encodeURIComponent(sessionId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchResearchSessionReport(sessionId: string): Promise<string> {
  const response = await fetch(`${API_URL}/research_sessions/${encodeURIComponent(sessionId)}/report`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return ((await response.json()) as { markdown: string }).markdown;
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

export async function fetchCampaignSummary(campaignId: string, language: string): Promise<PlainSummary> {
  const response = await fetch(`${API_URL}/campaign/${encodeURIComponent(campaignId)}/summary?lang=${language}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchGlossary(language: string): Promise<Record<string, { term: string; explanation: string }>> {
  const response = await fetch(`${API_URL}/glossary?lang=${language}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return ((await response.json()) as { terms: Record<string, { term: string; explanation: string }> }).terms;
}

export type Vocabulary = { models: Record<string, string>; datasets: Record<string, string>; metrics: Record<string, string> };

export async function fetchVocabulary(language: string): Promise<Vocabulary> {
  const response = await fetch(`${API_URL}/vocabulary?lang=${language}`);
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
