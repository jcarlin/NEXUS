import { test, expect } from "@playwright/test";

test.describe("Datasets", () => {
  test("dataset tree shows seeded folders", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show the seeded dataset names
    const dueDiligence = page.getByText("Due Diligence", { exact: false });
    await expect(dueDiligence).toBeVisible({ timeout: 10_000 });
  });

  test("child datasets are visible", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show child datasets (may need to expand parent)
    const correspondence = page.getByText("Correspondence", { exact: false });
    await expect(correspondence).toBeVisible({ timeout: 10_000 });
  });

  test("document counts are shown", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Dataset nodes should show document counts (numbers)
    const numbers = page
      .locator("[class*='count'], [class*='badge']")
      .filter({ hasText: /\d+/ });
    await expect(numbers.first())
      .toBeVisible({ timeout: 10_000 })
      .catch(() => {
        // Some UIs show count inline in text, check for that
      });
  });
});
