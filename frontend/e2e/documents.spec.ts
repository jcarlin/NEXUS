import { test, expect } from "@playwright/test";

test.describe("Documents", () => {
  test("document list shows seeded documents", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Table should have rows with document data
    const rows = page.locator("table tbody tr, [role='row']");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Should have at least 10 documents from seeding
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(10);
  });

  test("click document navigates to detail page", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Click first document filename link
    const firstLink = page.locator("table tbody tr a").first();
    await firstLink.click();

    // Should navigate to a document detail page
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });

    // Detail page should show filename and metadata
    await page.waitForTimeout(2_000);
    const heading = page.locator("h1, h2, h3").first();
    await expect(heading).toBeVisible();
  });

  test("import page renders upload form", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Should have a file input or upload area
    const uploadArea = page
      .locator(
        "input[type='file'], [class*='upload'], [class*='dropzone']",
      )
      .first();
    await expect(uploadArea).toBeAttached({ timeout: 10_000 });
  });
});
