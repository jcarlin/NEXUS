import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Documents Import", () => {
  test("import page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("page renders with heading and description", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Ingest Documents" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Upload files or ingest from a server-side source."),
    ).toBeVisible();
  });

  test("upload mode is default and shows upload widget", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Upload Files card should be the default selected mode
    await expect(
      page.getByText("Upload Files", { exact: true }),
    ).toBeVisible({ timeout: 10_000 });

    // Upload widget should be visible (file input or dropzone)
    const uploadArea = page
      .locator(
        "input[type='file'], [class*='upload'], [class*='dropzone'], [data-testid='upload-widget']",
      )
      .first();
    await expect(uploadArea).toBeAttached({ timeout: 10_000 });
  });

  test("server source mode renders ingest form", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Click Server Source card — use the role-based locator from the button
    const serverCard = page.getByRole("button", {
      name: /Server Source/i,
    });
    await expect(serverCard).toBeVisible({ timeout: 10_000 });
    await serverCard.click();
    await page.waitForTimeout(1_000);

    // Should show server ingest form with source type selector
    await expect(page.getByText("Source Type")).toBeVisible({ timeout: 5_000 });
  });

  test("EDRM mode renders format selector", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Click EDRM card
    const edrmCard = page.getByText("EDRM / Load File");
    await expect(edrmCard).toBeVisible({ timeout: 10_000 });
    await edrmCard.click();
    await page.waitForTimeout(1_000);

    // Should show EDRM format select and file input
    const formatSelect = page.locator("#edrm-format");
    await expect(formatSelect).toBeVisible({ timeout: 5_000 });

    const fileInput = page.locator("#edrm-file");
    await expect(fileInput).toBeAttached();

    // Import button should be present
    await expect(
      page.getByRole("button", { name: /Import Load File/i }),
    ).toBeVisible();
  });

  test("all three ingest mode cards are present", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByText("Upload Files", { exact: true }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Server Source", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("EDRM / Load File", { exact: true }),
    ).toBeVisible();
  });

  test("ingest history section shows past jobs", async ({ page }) => {
    await page.goto("/documents/import", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Ingest History heading should be visible if there are past jobs
    const historyHeading = page.getByText("Ingest History");
    if (await historyHeading.isVisible().catch(() => false)) {
      // Table should have expected columns
      await expect(page.getByText("Date")).toBeVisible();
      await expect(page.getByText("Source")).toBeVisible();
      await expect(page.getByText("Status")).toBeVisible();
    }
  });
});
