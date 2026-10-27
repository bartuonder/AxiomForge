import { expect, test } from "@playwright/test";
import { common, mockApi, type Call } from "./support";

const STEPS = [
  { id: "literature_node", phase: "done" },
  { id: "planner_node", phase: "done" },
  { id: "experiment_node", phase: "active" },
];

function snapshot(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    thread_id: "t-1",
    mode: "experiment",
    status: "running",
    next: ["experiment_node"],
    active_step: "experiment_node",
    hypotheses: ["h"],
    experiment_specs: [],
    selected_hypothesis: 0,
    approval_status: "approved",
    verification_status: "",
    verifier_feedback: "",
    instability: { unstable: false, std_threshold: 0.05, flagged: [] },
    research_status: "",
    consistency_feedback: "",
    referee_notes: [],
    error: "",
    error_info: null,
    can_retry: false,
    steps: STEPS,
    campaign_specs: [],
    campaign_id: "",
    campaign_status: "",
    ...overrides,
  };
}

const FAILED = snapshot({
  status: "failed",
  error: "[sandbox_error] boom",
  error_info: { code: "sandbox_error", title: "Deney çalıştırılamadı", message: "Kod hata verdi.", hint: "Yeniden deneyin.", technical: "boom" },
  can_retry: true,
});

test("a failed research can be started again from where it stopped", async ({ page }) => {
  let retried = false;
  const calls = await mockApi(page, (call: Call) => {
    if (call.method === "POST" && call.path === "/start_research") {
      return { thread_id: "t-1", status: "running", mode: "experiment" };
    }
    if (call.method === "POST" && call.path === "/research/t-1/retry") {
      retried = true;
      return { thread_id: "t-1", status: "running", action: "resume" };
    }
    if (call.path === "/research/t-1") {
      return retried ? snapshot() : FAILED;
    }
    return common(call);
  });
  await page.goto("/");
  await page.getByRole("radio", { name: /Tek deney/ }).check();
  await page.getByRole("textbox").fill("RandomForest ve SVM modellerini karşılaştır");
  await page.getByRole("button", { name: "Sınamayı başlat" }).click();
  await expect(page.getByText("Deney çalıştırılamadı")).toBeVisible();
  await page.getByRole("button", { name: "Kaldığı yerden yeniden dene" }).click();
  await expect(page.getByText("Deney çalıştırılamadı")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Kaldığı yerden yeniden dene" })).toHaveCount(0);
  expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual(["/start_research", "/research/t-1/retry"]);
});

test("a failure that cannot be resumed offers no retry", async ({ page }) => {
  await mockApi(page, (call: Call) => {
    if (call.method === "POST" && call.path === "/start_research") {
      return { thread_id: "t-1", status: "running", mode: "experiment" };
    }
    if (call.path === "/research/t-1") {
      return { ...FAILED, can_retry: false };
    }
    return common(call);
  });
  await page.goto("/");
  await page.getByRole("radio", { name: /Tek deney/ }).check();
  await page.getByRole("textbox").fill("RandomForest ve SVM modellerini karşılaştır");
  await page.getByRole("button", { name: "Sınamayı başlat" }).click();
  await expect(page.getByText("Deney çalıştırılamadı")).toBeVisible();
  await expect(page.getByRole("button", { name: "Kaldığı yerden yeniden dene" })).toHaveCount(0);
});

test("the report page of a stopped research can also be retried", async ({ page }) => {
  let retried = false;
  await mockApi(page, (call: Call) => {
    if (call.method === "POST" && call.path === "/research/t-1/retry") {
      retried = true;
      return { thread_id: "t-1", status: "running", action: "resume" };
    }
    if (call.path === "/research/t-1") {
      return retried ? snapshot() : FAILED;
    }
    return common(call);
  });
  await page.goto("/result/t-1");
  await expect(page.getByText("Deney çalıştırılamadı")).toBeVisible();
  await page.getByRole("button", { name: "Kaldığı yerden yeniden dene" }).click();
  await expect(page.getByText("Araştırma sürüyor")).toBeVisible();
  await expect(page.getByText("Deney çalıştırılamadı")).toHaveCount(0);
});
