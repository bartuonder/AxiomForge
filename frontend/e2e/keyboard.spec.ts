import { expect, test } from "@playwright/test";
import { common, mockApi, REPORT, summary, type Call } from "./support";

const RUNNING = summary({
  claims: [],
  status: { code: "running", label: "Çalışıyor", tone: "neutral" },
  progress: { finished: 3, failed: 0, total: 9, percent: 33 },
  live: { running: [], eta_seconds: null, cancel_requested: false },
  actions: { cancel: true, retry: false },
});

function routes(call: Call): unknown {
  switch (call.path) {
    case "/campaign/done/summary":
      return summary({ campaign_id: "done" });
    case "/campaign/done/report":
      return REPORT;
    case "/campaign/run/summary":
      return RUNNING;
    default:
      return common(call);
  }
}

test("the tabs follow the arrow keys, Home and End and only the selected tab is in the tab order", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/campaign/done");
  const summaryTab = page.getByRole("tab", { name: "Özet" });
  const reportTab = page.getByRole("tab", { name: "Ayrıntılı rapor" });
  const evidenceTab = page.getByRole("tab", { name: "Kanıtlar" });
  await expect(summaryTab).toHaveAttribute("tabindex", "0");
  await expect(reportTab).toHaveAttribute("tabindex", "-1");
  await summaryTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(reportTab).toBeFocused();
  await expect(reportTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toBeVisible();
  await page.keyboard.press("End");
  await expect(evidenceTab).toBeFocused();
  await expect(evidenceTab).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowRight");
  await expect(summaryTab).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(evidenceTab).toBeFocused();
  await page.keyboard.press("Home");
  await expect(summaryTab).toBeFocused();
  await expect(summaryTab).toHaveAttribute("aria-selected", "true");
});

test("a glossary term shows its explanation when it gets the keyboard focus", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/campaign/done");
  const term = page.locator("button[aria-describedby]").first();
  await expect(page.getByRole("tooltip").first()).toBeHidden();
  await term.focus();
  await expect(page.getByRole("tooltip").first()).toBeVisible();
  await expect(page.getByRole("tooltip").first()).toContainText("Gerçek bir veri tablosu.");
});

test("the cancel question can be answered and dismissed with the keyboard", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/campaign/run");
  const cancel = page.getByRole("button", { name: "Kampanyayı iptal et" });
  await cancel.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Vazgeç" }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await cancel.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Evet, iptal et" }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
});

test("the keyboard focus is always visible", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/");
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement as Element);
    return { width: style.outlineWidth, style: style.outlineStyle };
  });
  expect(outline.style).toBe("solid");
  expect(outline.width).toBe("2px");
});

test("an example can be chosen with the keyboard alone", async ({ page }) => {
  await mockApi(page, routes);
  await page.goto("/");
  const example = page.getByRole("button", { name: "Random forest, tek bir karar ağacından daha mı iyi?" });
  await example.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox")).toHaveValue(/Random forests outperform a single decision tree/);
});
