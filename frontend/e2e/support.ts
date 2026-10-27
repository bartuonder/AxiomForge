import type { Page, Route } from "@playwright/test";

export type Call = { method: string; path: string };

export type Handler = (call: Call, route: Route) => unknown | Promise<unknown>;

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET, POST, OPTIONS",
};

export async function mockApi(page: Page, handler: Handler): Promise<Call[]> {
  const calls: Call[] = [];
  await page.route(/127\.0\.0\.1:8000/, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const url = new URL(request.url());
    const call = { method: request.method(), path: url.pathname };
    calls.push(call);
    const body = await handler(call, route);
    if (body === undefined) {
      await route.fulfill({ status: 404, headers: CORS, contentType: "application/json", body: JSON.stringify({ detail: "not mocked" }) });
      return;
    }
    await route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
  });
  return calls;
}

export const GLOSSARY = { terms: { dataset: { term: "Veri seti", explanation: "Gerçek bir veri tablosu." } } };

export const VOCABULARY = { models: {}, datasets: {}, metrics: {} };

export function common(call: Call): unknown {
  if (call.path === "/glossary") {
    return GLOSSARY;
  }
  if (call.path === "/vocabulary") {
    return VOCABULARY;
  }
  return undefined;
}

export function summary(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    language: "tr",
    campaign_id: "demo",
    title: "Ağaçlar sinir ağlarına karşı",
    source: null,
    status: { code: "completed", label: "Tamamlandı", tone: "positive" },
    progress: { finished: 9, failed: 0, total: 9, percent: 100 },
    live: { running: [], eta_seconds: null, cancel_requested: false },
    actions: { cancel: false, retry: false },
    recoveries: 0,
    headline: "Random Forest, Karar ağacı modelinden daha iyi çıktı",
    verdict_counts: { replicated: 1 },
    claims: [
      {
        id: "C1",
        statement: "Forests beat a tree",
        verdict: { code: "replicated", label: "Doğrulandı", tone: "positive", meaning: "İddia tutarlı biçimde doğru çıktı." },
        headline: "Random Forest, Karar ağacı modelinden daha iyi çıktı",
        confidence: { level: "high", label: "Yüksek güven", reason: "Tüm ölçütlerde aynı sonuç çıktı." },
        primary_metric: "roc_auc",
        datasets_for: 9,
        datasets_against: 0,
        datasets_total: 9,
        metrics: [],
        chart: { metric: "roc_auc", metric_label: "ROC-AUC", subject_label: "Random Forest", other_label: "Karar ağacı", points: [{ dataset: "a", label: "Kredi riski", subject: 0.85, other: 0.8 }] },
      },
    ],
    ranking: [],
    method: ["9 gerçek veri setinde denendi."],
    cautions: [],
    datasets: [{ key: "a", label: "Kredi riski" }],
    glossary: {},
    error: null,
    error_info: null,
    ...overrides,
  };
}

export const REPORT = { markdown: "# Rapor\n\nMetin.\n\n## Evidence ledger\n\n| a |\n", ledger: [] };
