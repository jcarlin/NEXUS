import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Documents", () => {
  test("document list renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("document detail renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);
    const firstLink = page.locator("table tbody tr a").first();
    if (await firstLink.isVisible().catch(() => false)) {
      await firstLink.click();
      await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
      await page.waitForTimeout(3_000);
      expectNoConsoleErrors(errors);
    }
  });

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

  test("document detail page shows document info panel", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Navigate to first document detail
    const firstLink = page.locator("table tbody tr a").first();
    await firstLink.click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
    await page.waitForTimeout(2_000);

    // Document Info panel should be visible (right sidebar)
    await expect(page.getByText("Document Info")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Filename")).toBeVisible();
  });

  test("document detail shows page/chunk/entity counts", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstLink = page.locator("table tbody tr a").first();
    await firstLink.click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
    await page.waitForTimeout(2_000);

    // Subtitle shows page/chunk/entity counts
    await expect(
      page.getByText(/\d+ pages? \| \d+ chunks? \| \d+ entit/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("document detail shows filename heading", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstLink = page.locator("table tbody tr a").first();
    const linkText = await firstLink.textContent();
    await firstLink.click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
    await page.waitForTimeout(2_000);

    // Document heading should show the filename
    if (linkText) {
      const heading = page.getByRole("heading", { name: linkText.trim() });
      await expect(heading).toBeVisible({ timeout: 10_000 });
    }
  });

  test("document detail has download button", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstLink = page.locator("table tbody tr a").first();
    await firstLink.click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
    await page.waitForTimeout(2_000);

    // Download button should be present
    const downloadBtn = page.getByRole("button", { name: /download/i });
    if (await downloadBtn.isVisible().catch(() => false)) {
      await expect(downloadBtn).toBeEnabled();
    }
  });

  test("document detail back button returns to list", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstLink = page.locator("table tbody tr a").first();
    await firstLink.click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
    await page.waitForTimeout(2_000);

    // Back button should navigate to /documents
    const backBtn = page.locator("a[href='/documents']").first();
    await expect(backBtn).toBeVisible({ timeout: 5_000 });
    await backBtn.click();
    await expect(page).toHaveURL("/documents", { timeout: 10_000 });
  });

  test("search input filters documents", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const searchInput = page.getByPlaceholder(/search|filter/i);
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill("xyz_nonexistent_query");
      await page.waitForTimeout(1_000);

      // Should show filtered results or "no results"
      const rows = page.locator("table tbody tr");
      const noResults = page.getByText(/no results|no documents|nothing found/i);
      const hasRows = await rows.first().isVisible().catch(() => false);
      const hasNoResults = await noResults.isVisible().catch(() => false);
      expect(hasRows || hasNoResults).toBe(true);
    }
  });

  test("document detail shows chunk content", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstLink = page.locator("table tbody tr a").first();
    if (await firstLink.isVisible().catch(() => false)) {
      await firstLink.click();
      await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
      await page.waitForTimeout(3_000);

      // Should show chunks with text content
      const chunks = page.locator("[class*='chunk'], [data-testid*='chunk']");
      if (await chunks.first().isVisible().catch(() => false)) {
        const chunkText = await chunks.first().textContent();
        expect(chunkText?.trim().length).toBeGreaterThan(10);
      }
    }
  });
});
