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
});
