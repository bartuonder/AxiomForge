import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { common, mockApi, type Call } from "./support";

const SUMMARY = {
  id: "real-1",
  status: "completed",
  reason: "",
  created: "2026-10-28T10:00:00+00:00",
  finished: "2026-10-28T11:00:00+00:00",
  models: ["RandomForest", "LogisticRegression"],
  explore: ["tb_credit", "tb_pol"],
  confirm: ["tb_eye", "tb_bank"],
  budget: 25,
  registered: 2,
  counts: { confirmed: 1, reversed: 0, not_confirmed: 1, not_testable: 0 },
  stages: [{ name: "default", finished: 16, failed: 0 }],
};

const HYPOTHESES = [
  { id: "H1", subject: ["RandomForest"], other: ["LogisticRegression"], stage: "default", metric: "roc_auc", statement: "x", evidence: { median_difference: 0.04, wins: 5, datasets: 6, scope: "exploration" }, digest: "d1", registered_at: "t" },
  { id: "H2", subject: ["LogisticRegression"], other: ["RandomForest"], stage: "tuned", metric: "roc_auc", statement: "y", evidence: { median_difference: 0.012, wins: 5, datasets: 6, scope: "exploration" }, digest: "d2", registered_at: "t" },
];

const CONFIRMATIONS = [
  { id: "H1", stage: "default", status: "confirmed", p_value: 0.0004, adjusted_p_value: 0.008, q_value: 0.004, median_difference: 0.031, wins: 10, losses: 0, ties: 0, datasets: 10 },
  { id: "H2", stage: "tuned", status: "not_confirmed", p_value: 0.2, adjusted_p_value: 0.4, q_value: 0.2, median_difference: -0.002, wins: 4, losses: 6, ties: 0, datasets: 10 },
];

function detail(overrides: Record<string, unknown> = {}, intact = true, summary: Record<string, unknown> = {}): unknown {
  return { summary: { ...SUMMARY, ...summary }, intact, session: { hypotheses: HYPOTHESES, confirmations: CONFIRMATIONS, skipped: [{ stage: "default", statement: "A beats B", reason: "already confirmed in an earlier session" }], ...overrides } };
}

function routes(options: { intact?: boolean; running?: boolean } = {}) {
  return (call: Call): unknown => {
    if (call.path === "/research_sessions") {
      return { items: [SUMMARY, { ...SUMMARY, id: "demo-2", status: "aborted", reason: "only 2 of 6 exploration datasets finished", registered: 0, counts: { confirmed: 0, reversed: 0, not_confirmed: 0, not_testable: 0 } }] };
    }
    if (call.path === "/research_sessions/real-1") {
      return detail({}, options.intact ?? true, options.running ? { status: "running" } : {});
    }
    if (call.path === "/research_sessions/real-1/report") {
      return { markdown: "# Research session real-1\n" };
    }
    if (call.path === "/vocabulary") {
      return { models: { RandomForest: "Random Forest", LogisticRegression: "Lojistik regresyon" }, datasets: { tb_credit: "Kredi riski", tb_pol: "Telekomünikasyon verisi", tb_eye: "Okurken göz hareketleri", tb_bank: "Banka pazarlama kampanyası" }, metrics: {} };
    }
    return common(call);
  };
}

test("the sessions are listed with their status and counts", async ({ page }) => {
  await mockApi(page, routes());
  await page.goto("/research");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Araştırma ajanı oturumları");
  await expect(page.getByRole("link", { name: /real-1/ })).toBeVisible();
  await expect(page.getByText("2 hipotez kaydedildi, 1 doğrulandı")).toBeVisible();
  await expect(page.getByText("Yarıda kaldı")).toBeVisible();
});

test("a session explains the protocol and shows each hypothesis with its two effects", async ({ page }) => {
  await mockApi(page, routes());
  await page.goto("/research/real-1");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Araştırma oturumu real-1");
  await expect(page.getByText("2 hipotez kaydedildi: 1 doğrulandı, 0 tersi çıktı, 1 doğrulanamadı, 0 test edilemedi.")).toBeVisible();
  await expect(page.getByRole("row", { name: /Random Forest ≻ Lojistik regresyon/ })).toContainText("Doğrulandı");
  await expect(page.getByRole("row", { name: /Lojistik regresyon ≻ Random Forest/ })).toContainText("Doğrulanamadı");
  await expect(page.getByText("Kayıtlı hipotezler, kayıttan beri değiştirilmedi.")).toBeVisible();
  await expect(page.getByText("A beats B: already confirmed in an earlier session")).toBeVisible();
  await expect(page.getByText("Kredi riski, Telekomünikasyon verisi")).toBeVisible();
});

test("a changed registered hypothesis is announced as a warning", async ({ page }) => {
  await mockApi(page, routes({ intact: false }));
  await page.goto("/research/real-1");
  await expect(page.locator("[role=alert]", { hasText: "sonuçlara güvenmeyin" })).toBeVisible();
});

test("the report of a finished session can be downloaded and a running session offers none", async ({ page }) => {
  await mockApi(page, routes());
  await page.goto("/research/real-1");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Raporu indir (.md)" }).click();
  expect((await download).suggestedFilename()).toBe("real-1-report.md");
  const running = await page.context().newPage();
  await mockApi(running, routes({ running: true }));
  await running.goto("/research/real-1");
  await expect(running.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(running.getByRole("button", { name: "Raporu indir (.md)" })).toHaveCount(0);
});

test("a session that does not exist says so", async ({ page }) => {
  await mockApi(page, (call) => (call.path.startsWith("/research_sessions/") ? undefined : routes()(call)));
  await page.goto("/research/nope");
  await expect(page.getByText("Oturum yüklenemedi.").or(page.getByText("not mocked"))).toBeVisible();
});

test("the research pages have no accessibility violations in both themes", async ({ page }) => {
  await mockApi(page, routes());
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const path of ["/research", "/research/real-1"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(result.violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).join(" | ")}`), `${scheme} ${path}`).toEqual([]);
    }
  }
});
