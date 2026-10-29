import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { common, mockApi, type Call } from "./support";

const BASE = {
  id: "r-1",
  reason: "",
  created: "2026-10-28T10:00:00+00:00",
  finished: "",
  models: ["RandomForest", "LogisticRegression"],
  explore: ["tb_credit"],
  confirm: ["tb_eye"],
  budget: 25,
  registered: 0,
  counts: { confirmed: 0, reversed: 0, not_confirmed: 0, not_testable: 0 },
  phase: "",
  stages: [],
};

function detail(status: string, extra: Record<string, unknown> = {}, session: Record<string, unknown> = {}): unknown {
  return { summary: { ...BASE, status, ...extra }, intact: true, session: { hypotheses: [], ...session } };
}

const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET, POST, OPTIONS" };

test("a session is started from the form with the chosen models and opens its page", async ({ page }) => {
  const bodies: unknown[] = [];
  await mockApi(page, (call: Call, route) => {
    if (call.method === "POST" && call.path === "/start_research_session") {
      bodies.push(route.request().postDataJSON());
      return { session_id: "r-1", status: "queued" };
    }
    if (call.path === "/research_sessions") {
      return { items: [] };
    }
    if (call.path === "/research_sessions/r-1") {
      return detail("queued");
    }
    return common(call);
  });
  await page.goto("/research");
  const start = page.getByRole("button", { name: "Oturumu başlat" });
  await expect(start).toBeEnabled();
  for (const name of ["ExtraTrees", "GradientBoosting", "HistGradientBoosting", "MLP", "RandomForest"]) {
    await page.getByRole("checkbox", { name, exact: true }).uncheck();
  }
  await expect(start).toBeDisabled();
  await expect(page.getByText("Başlatmak için en az iki model seçin.")).toBeVisible();
  await page.getByRole("checkbox", { name: "MLP", exact: true }).check();
  await page.getByRole("checkbox", { name: "Ayarlı aşamayı da çalıştır" }).check();
  await expect(start).toBeEnabled();
  await start.click();
  await expect(page).toHaveURL(/\/research\/r-1$/);
  await expect(page.getByText("Sırada: bir işçi süreci bekleniyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toHaveCount(0);
  expect(bodies).toEqual([{ models: ["MLP", "LogisticRegression"], generator: "rules", tuning: 12 }]);
});

test("a refused start shows the reason and keeps the form", async ({ page }) => {
  await mockApi(page, (call: Call) => (call.path === "/research_sessions" ? { items: [] } : common(call)));
  await page.route(/start_research_session/, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    await route.fulfill({ status: 429, headers: CORS, contentType: "application/json", body: JSON.stringify({ detail: "[daily_limit] the limit of 100 starts per day has been reached" }) });
  });
  await page.goto("/research");
  await page.getByRole("button", { name: "Oturumu başlat" }).click();
  await expect(page.locator("p[role=alert]")).toContainText("100");
  await expect(page).toHaveURL(/\/research$/);
  await expect(page.getByRole("button", { name: "Oturumu başlat" })).toBeEnabled();
});

test("a running session shows its stage, can be cancelled after a question and then offers to start again", async ({ page }) => {
  let cancelled = false;
  const calls = await mockApi(page, (call: Call) => {
    if (call.method === "POST" && call.path === "/research_sessions/r-1/cancel") {
      cancelled = true;
      return { status: "running", cancel_requested: true };
    }
    if (call.path === "/research_sessions/r-1") {
      return cancelled ? detail("cancelled", { reason: "stopped on request" }) : detail("running", { phase: "default" });
    }
    return common(call);
  });
  await page.goto("/research/r-1");
  await expect(page.getByText("Varsayılan ayarlarla deneyler çalışıyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toHaveCount(0);
  await page.getByRole("button", { name: "Oturumu iptal et" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  expect(calls.filter((call) => call.method === "POST")).toEqual([]);
  await page.getByRole("button", { name: "Oturumu iptal et" }).click();
  await page.getByRole("button", { name: "Evet, iptal et" }).click();
  await expect(page.getByRole("button", { name: "Yeniden başlat" })).toBeVisible();
  await expect(page.getByText("İptal edildi")).toBeVisible();
  expect(calls.filter((call) => call.method === "POST")).toEqual([{ method: "POST", path: "/research_sessions/r-1/cancel" }]);
});

test("a pending cancel request is announced and its button is gone", async ({ page }) => {
  await mockApi(page, (call: Call) => (call.path === "/research_sessions/r-1" ? detail("running", { phase: "default" }, { cancel_requested: true }) : common(call)));
  await page.goto("/research/r-1");
  await expect(page.getByText("İptal isteniyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Oturumu iptal et" })).toHaveCount(0);
});

test("a session whose worker died can be started again", async ({ page }) => {
  let retried = false;
  const calls = await mockApi(page, (call: Call) => {
    if (call.method === "POST" && call.path === "/research_sessions/r-1/retry") {
      retried = true;
      return { session_id: "r-1", status: "queued" };
    }
    if (call.path === "/research_sessions/r-1") {
      return retried ? detail("queued") : detail("failed", { reason: "the worker of this session stopped reporting" }, { stale: true });
    }
    return common(call);
  });
  await page.goto("/research/r-1");
  await expect(page.getByText("Bu oturumu çalıştıran işçi süreci yanıt vermeyi kesti.")).toBeVisible();
  await page.getByRole("button", { name: "Yeniden başlat" }).click();
  await expect(page.getByText("Sırada: bir işçi süreci bekleniyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Yeniden başlat" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Oturumu iptal et" })).toBeVisible();
  expect(calls.filter((call) => call.method === "POST")).toEqual([{ method: "POST", path: "/research_sessions/r-1/retry" }]);
});

test("the form and the session controls have no accessibility violations in both themes", async ({ page }) => {
  await mockApi(page, (call: Call) => {
    if (call.path === "/research_sessions") {
      return { items: [{ ...BASE, status: "running", phase: "default" }] };
    }
    if (call.path === "/research_sessions/r-1") {
      return detail("failed", { reason: "boom" }, { stale: true });
    }
    return common(call);
  });
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const path of ["/research", "/research/r-1"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(result.violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).join(" | ")}`), `${scheme} ${path}`).toEqual([]);
    }
  }
});

test("a queued session refreshes itself until it is running and then finished", async ({ page }) => {
  let reads = 0;
  await mockApi(page, (call: Call) => {
    if (call.path === "/research_sessions/r-1") {
      reads += 1;
      if (reads === 1) {
        return detail("queued");
      }
      return reads === 2 ? detail("running", { phase: "tuned" }) : detail("completed", { finished: "2026-10-28T11:00:00+00:00" });
    }
    return common(call);
  });
  await page.goto("/research/r-1");
  await expect(page.getByText("Sırada: bir işçi süreci bekleniyor.")).toBeVisible();
  await expect(page.getByText("Ayarlı aşamanın deneyleri çalışıyor.")).toBeVisible({ timeout: 12_000 });
  await expect(page.getByRole("button", { name: "Raporu indir (.md)" })).toBeVisible({ timeout: 12_000 });
  await expect(page.getByText("Ayarlı aşamanın deneyleri çalışıyor.")).toHaveCount(0);
});

test("a running session shows how many datasets finished and which ones run, and the bar moves", async ({ page }) => {
  let reads = 0;
  await mockApi(page, (call: Call) => {
    if (call.path === "/research_sessions/r-1") {
      reads += 1;
      const progress = reads === 1 ? { stage: "default", total: 16, finished: 4, failed: 0, running: ["tb_credit", "tb_eye"] } : { stage: "default", total: 16, finished: 9, failed: 1, running: ["tb_pol"] };
      return detail("running", { phase: "default", progress });
    }
    return common(call);
  });
  await page.goto("/research/r-1");
  const bar = page.getByRole("progressbar", { name: "Veri seti ilerlemesi" });
  await expect(bar).toHaveAttribute("aria-valuenow", "25");
  await expect(page.getByText("4 / 16 veri seti bitti.")).toBeVisible();
  await expect(page.getByText("Şu an çalışan: tb_credit, tb_eye")).toBeVisible();
  await expect(bar).toHaveAttribute("aria-valuenow", "63", { timeout: 12_000 });
  await expect(page.getByText("10 / 16 veri seti bitti. (1 tanesi başarısız oldu.)")).toBeVisible();
  await expect(page.getByText("Şu an çalışan: tb_pol")).toBeVisible();
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(result.violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).join(" | ")}`), scheme).toEqual([]);
  }
});
