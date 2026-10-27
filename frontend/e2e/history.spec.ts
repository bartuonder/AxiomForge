import { expect, test } from "@playwright/test";
import { common, mockApi } from "./support";

const ITEMS = [
  { id: "u1", title: "Kullanıcı sorusu", statement: "Forests beat trees", origin: "console", status: "completed", updated: "2026-10-27T10:00:00+00:00", datasets: 9, finished: 9, failed: 0, verdicts: [{ id: "C1", verdict: "replicated" }] },
  { id: "t1", title: "Benchmark run", statement: "Bench", origin: "cli", status: "completed", updated: "2026-10-26T10:00:00+00:00", datasets: 9, finished: 9, failed: 0, verdicts: [] },
];

test.beforeEach(async ({ page }) => {
  await mockApi(page, (call) => (call.path === "/campaigns" ? { campaigns: ["u1", "t1"], items: ITEMS } : common(call)));
});

test("test and benchmark runs are hidden until asked for", async ({ page }) => {
  await page.goto("/campaigns");
  await expect(page.getByText("Kullanıcı sorusu")).toBeVisible();
  await expect(page.getByText("Benchmark run")).toHaveCount(0);
  await page.getByLabel(/Test ve kıyas çalışmalarını da göster/).check();
  await expect(page.getByText("Benchmark run")).toBeVisible();
});

test("the search narrows the list", async ({ page }) => {
  await page.goto("/campaigns");
  await page.getByLabel("İddia ara").fill("yok böyle bir şey");
  await expect(page.getByText("Kullanıcı sorusu")).toHaveCount(0);
  await page.getByLabel("İddia ara").fill("forests");
  await expect(page.getByText("Kullanıcı sorusu")).toBeVisible();
});
