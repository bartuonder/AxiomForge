import { API_URL, type ResearchSnapshot } from "@/lib/types";

export async function startResearch(query: string): Promise<{ thread_id: string }> {
  const response = await fetch(`${API_URL}/start_research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
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

export async function approvePlan(threadId: string, decision: "Y" | "N"): Promise<void> {
  const response = await fetch(`${API_URL}/approve_plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, decision }),
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

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || response.statusText;
  } catch {
    return response.statusText;
  }
}
