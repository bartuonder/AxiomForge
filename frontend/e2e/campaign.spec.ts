import { expect, test } from "@playwright/test";
import { common, mockApi, REPORT, summary } from "./support";

const RUNNING = summary({
  claims: [],
  status: { code: "running", label: "Çalışıyor", tone: "neutral" },
  progress: { finished: 3, failed: 0, total: 9, percent: 33 },
  live: { running: [{ key: "a", label: "Kredi riski" }], eta_seconds: 420, cancel_requested: false },
  actions: { cancel: true, retry: false },
});

function finished(call: { path: string }): unknown {
  if (call.path === "/campaign/demo/summary") {
    return summary();
  }
  return call.path === "/campaign/demo/report" ? REPORT : undefined;
}

test("a finished campaign shows the answer first and the details on request", async ({ page }) => {
  await mockApi(page, (call) => common(call) ?? finished(call));
  await page.goto("/campaign/demo");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ağaçlar sinir ağlarına karşı");
  await expect(page.getByText("Doğrulandı").first()).toBeVisible();
  await expect(page.getByText("9 / 9").first()).toBeVisible();
  await page.getByRole("tab", { name: "Ayrıntılı rapor" }).click();
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toBeVisible();
  await expect(page.getByText("Evidence ledger")).toHaveCount(0);
});

test("the report can be downloaded as a Markdown file", async ({ page }) => {
  await mockApi(page, (call) => common(call) ?? finished(call));
  await page.goto("/campaign/demo");
  await page.getByRole("tab", { name: "Ayrıntılı rapor" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Raporu indir (.md)" }).click();
  expect((await download).suggestedFilename()).toBe("agaclar-sinir-aglarina-karsi-demo.md");
});

test("a running campaign shows progress and the time left, and can be cancelled after a confirmation", async ({ page }) => {
  let cancelled = false;
  const calls = await mockApi(page, (call) => {
    if (call.method === "POST" && call.path === "/campaign/demo/cancel") {
      cancelled = true;
      return { id: "demo", status: "cancelled" };
    }
    if (call.path === "/campaign/demo/summary") {
      return cancelled
        ? summary({ claims: [], status: { code: "cancelled", label: "İptal edildi", tone: "muted" }, actions: { cancel: false, retry: true }, progress: { finished: 3, failed: 0, total: 9, percent: 33 } })
        : RUNNING;
    }
    return common(call);
  });
  await page.goto("/campaign/demo");
  await expect(page.getByText("3 / 9 veri seti tamamlandı").first()).toBeVisible();
  await expect(page.getByText("Tahmini kalan süre: yaklaşık 7 dakika")).toBeVisible();
  await expect(page.getByText("Şu an çalışan veri setleri: Kredi riski")).toBeVisible();
  await page.getByRole("button", { name: "Kampanyayı iptal et" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  expect(calls.some((call) => call.method === "POST")).toBe(false);
  await page.getByRole("button", { name: "Vazgeç" }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Kampanyayı iptal et" }).click();
  await page.getByRole("button", { name: "Evet, iptal et" }).click();
  await expect(page.getByText("Bu kampanya iptal edildi, bu yüzden bir sonuç üretilmedi.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Yeniden başlat" })).toBeVisible();
  expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual(["/campaign/demo/cancel"]);
});

test("a failed campaign explains why and can be started again", async ({ page }) => {
  let retried = false;
  const failed = summary({
    claims: [],
    status: { code: "failed", label: "Başarısız", tone: "negative" },
    actions: { cancel: false, retry: true },
    error: "the campaign has reported no progress for 30 minutes; its worker may have stopped",
    error_info: { code: "stale_worker", title: "İşlem uzun süredir ilerlemiyor", message: "Arka planda çalışan sürecin durmuş olabileceği düşünülüyor.", hint: "Yeniden başlatın.", technical: "no progress" },
  });
  const calls = await mockApi(page, (call) => {
    if (call.method === "POST" && call.path === "/campaign/demo/retry") {
      retried = true;
      return { campaign_id: "demo", status: "queued" };
    }
    if (call.path === "/campaign/demo/summary") {
      return retried
        ? summary({ claims: [], status: { code: "queued", label: "Sırada", tone: "muted" }, actions: { cancel: true, retry: false }, recoveries: 1, progress: { finished: 0, failed: 0, total: 9, percent: 0 } })
        : failed;
    }
    return common(call);
  });
  await page.goto("/campaign/demo");
  await expect(page.getByText("İşlem uzun süredir ilerlemiyor")).toBeVisible();
  await page.getByRole("button", { name: "Yeniden başlat" }).click();
  await expect(page.getByText("Kampanya sırada bekliyor.")).toBeVisible();
  await expect(page.getByText("1 kez yeniden başlatıldı")).toBeVisible();
  expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual(["/campaign/demo/retry"]);
});

test("a refused request is explained in plain words", async ({ page }) => {
  await mockApi(page, (call) => {
    if (call.method === "POST") {
      return undefined;
    }
    return call.path === "/campaign/demo/summary" ? RUNNING : common(call);
  });
  await page.route(/127\.0\.0\.1:8000\/campaign\/demo\/cancel/, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 401,
      headers: { "access-control-allow-origin": "*" },
      contentType: "application/json",
      body: JSON.stringify({ detail: "[unauthorized] missing key" }),
    });
  });
  await page.goto("/campaign/demo");
  await page.getByRole("button", { name: "Kampanyayı iptal et" }).click();
  await page.getByRole("button", { name: "Evet, iptal et" }).click();
  await expect(page.locator("[role=alert]", { hasText: "erişim anahtarı" })).toBeVisible();
});
