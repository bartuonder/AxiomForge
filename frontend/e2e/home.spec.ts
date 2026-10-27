import { expect, test } from "@playwright/test";
import { common, mockApi } from "./support";

test.beforeEach(async ({ page }) => {
  await mockApi(page, (call) => common(call));
});

test("the home page explains what the system does in plain Turkish", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Bir iddianın doğru olup olmadığını gerçek verilerle sınayın");
  await expect(page.getByRole("button", { name: "Sınamayı başlat" })).toBeDisabled();
});

test("an example fills the question and enables the start button", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Random forest, tek bir karar ağacından daha mı iyi?" }).click();
  await expect(page.getByRole("textbox")).toHaveValue(/Random forests outperform a single decision tree/);
  await expect(page.getByRole("button", { name: "Sınamayı başlat" })).toBeEnabled();
});

test("the language choice is applied at once and remembered", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /^en$/i }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Test whether a claim is true with real data");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Test whether a claim is true with real data");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("the theme can be switched and is remembered", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const light = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.getByRole("button", { name: "Koyu temaya geç" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(dark).not.toBe(light);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe(dark);
  await page.getByRole("button", { name: "Açık temaya geç" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe(light);
});

test("the dark theme follows the system until the user chooses", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Açık temaya geç" })).toBeVisible();
});
