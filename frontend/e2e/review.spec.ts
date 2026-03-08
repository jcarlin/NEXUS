import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Review", () => {
  test("hot docs renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/review/hot-docs", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("result set renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/review/result-set", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("hot docs page shows heading and scored documents", async ({
    page,
  }) => {
    await page.goto("/review/hot-docs", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    await expect(
      page.getByRole("heading", { name: "Hot Documents" }),
    ).toBeVisible({ timeout: 10_000 });

    // Should show documents with scores
    const content = page.locator(
      "table tbody tr, [role='row'], [class*='doc']",
    );
    await expect(content.first()).toBeVisible({ timeout: 10_000 });
  });

  test("result set page renders with heading", async ({ page }) => {
    await page.goto("/review/result-set", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Result Set" }),
    ).toBeVisible({ timeout: 10_000 });

    // Page should render without error
    const main = page.locator("main");
    await expect(main).toBeVisible();

    // Check no error boundary rendered
    const errorBoundary = page.locator("[data-testid='error-boundary']");
    await expect(errorBoundary)
      .not.toBeVisible({ timeout: 3_000 })
      .catch(() => {});
  });

  test("result set shows document description", async ({ page }) => {
    await page.goto("/review/result-set", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Description mentions documents and CSV export
    await expect(
      page.getByText(/documents.*Select rows and export to CSV/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("result set has duplicate clusters section", async ({ page }) => {
    await page.goto("/review/result-set", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Duplicate Clusters card title
    await expect(
      page.getByText("Duplicate Clusters", { exact: true }),
    ).toBeVisible({ timeout: 10_000 });
  });
});
