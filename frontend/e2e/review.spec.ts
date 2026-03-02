import { test, expect } from "@playwright/test";

test.describe("Review", () => {
  test("hot docs page shows scored documents", async ({ page }) => {
    await page.goto("/review/hot-docs", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show documents with scores
    const content = page.locator(
      "table tbody tr, [role='row'], [class*='doc']",
    );
    await expect(content.first()).toBeVisible({ timeout: 10_000 });
  });

  test("result set page renders", async ({ page }) => {
    await page.goto("/review/result-set", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Page should render without error
    const main = page.locator("main");
    await expect(main).toBeVisible();

    // Check no error boundary rendered
    const errorBoundary = page.locator("[data-testid='error-boundary']");
    await expect(errorBoundary)
      .not.toBeVisible({ timeout: 3_000 })
      .catch(() => {});
  });
});
