import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { common, mockApi, REPORT, summary, type Call } from "./support";

const RUNNING = summary({
  claims: [],
  status: { code: "running", label: "Çalışıyor", tone: "neutral" },
  progress: { finished: 3, failed: 0, total: 9, percent: 33 },
  live: { running: [{ key: "a", label: "Kredi riski" }], eta_seconds: 420, cancel_requested: false },
  actions: { cancel: true, retry: false },
});

const FAILED = summary({
  claims: [],
  status: { code: "failed", label: "Başarısız", tone: "negative" },
  actions: { cancel: false, retry: true },
  error: "boom",
  error_info: { code: "unknown", title: "Beklenmeyen bir hata oluştu", message: "İşlem tamamlanamadı.", hint: "Yeniden deneyin.", technical: "boom" },
});

const LIST = [
  { id: "u1", title: "Kullanıcı sorusu", statement: "Forests beat trees", origin: "console", status: "completed", updated: "2026-10-27T10:00:00+00:00", datasets: 9, finished: 9, failed: 0, verdicts: [{ id: "C1", verdict: "replicated" }] },
  { id: "u2", title: "Başarısız soru", statement: "x", origin: "console", status: "failed", updated: "2026-10-27T09:00:00+00:00", datasets: 9, finished: 2, failed: 1, verdicts: [] },
];

function routes(call: Call): unknown {
  switch (call.path) {
    case "/campaigns":
      return { campaigns: ["u1", "u2"], items: LIST };
    case "/campaign/done/summary":
      return summary({ campaign_id: "done" });
    case "/campaign/done/report":
      return REPORT;
    case "/campaign/run/summary":
      return RUNNING;
    case "/campaign/bad/summary":
      return FAILED;
    default:
      return common(call);
  }
}

async function violations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return result.violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).join(" | ")}`);
}

const PAGES = [
  { name: "the home page", path: "/" },
  { name: "the history", path: "/campaigns" },
  { name: "a finished campaign", path: "/campaign/done" },
  { name: "a running campaign", path: "/campaign/run" },
  { name: "a failed campaign", path: "/campaign/bad" },
];

for (const scheme of ["light", "dark"] as const) {
  for (const entry of PAGES) {
    test(`${entry.name} has no accessibility violations in the ${scheme} theme`, async ({ page }) => {
      await mockApi(page, routes);
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(entry.path);
      await page.waitForLoadState("networkidle");
      expect(await violations(page)).toEqual([]);
    });
  }
}

test("the report tab of a finished campaign has no accessibility violations", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/campaign/done");
  await page.getByRole("tab", { name: "Ayrıntılı rapor" }).click();
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test("the cancel confirmation has no accessibility violations", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/campaign/run");
  await page.getByRole("button", { name: "Kampanyayı iptal et" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  expect(await violations(page)).toEqual([]);
});
