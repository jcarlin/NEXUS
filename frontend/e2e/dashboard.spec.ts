import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("shows stat cards with data", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // The dashboard should have stat cards showing document/entity counts
    // Look for cards with numbers > 0
    const cards = page.locator("[class*='card']").filter({ hasText: /\d+/ });
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
  });

  test("renders recent activity widget", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Look for activity or recent items section
    const activity = page.getByText(/recent|activity|latest/i).first();
    await expect(activity).toBeVisible({ timeout: 10_000 });
  });

  test("stat cards show non-zero counts", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // At least one card should show a number > 0
    const numberTexts = page.locator("[class*='card'] [class*='text-2xl'], [class*='card'] [class*='text-3xl'], [class*='card'] .font-bold")
      .filter({ hasText: /^[1-9]\d*$/ });
    await expect(numberTexts.first()).toBeVisible({ timeout: 10_000 });
  });

  test("entity graph overview widget renders", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Entity overview section should be visible with graph data
    const graphSection = page.getByText(/entities|knowledge graph|graph overview/i).first();
    await expect(graphSection).toBeVisible({ timeout: 10_000 });
  });
});
