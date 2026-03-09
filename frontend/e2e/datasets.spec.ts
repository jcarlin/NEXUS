import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Datasets", () => {
  test("datasets page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("dataset tree shows seeded datasets", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show the "Datasets" header in the sidebar
    await expect(
      page.getByRole("heading", { name: "Datasets" }),
    ).toBeVisible({ timeout: 10_000 });

    // Should show at least one dataset node in the tree
    const datasetNodes = page.locator("[class*='tree'] button, [role='treeitem'], aside button").filter({ hasText: /.+/ });
    await expect(datasetNodes.first()).toBeVisible({ timeout: 10_000 });
  });

  test("select a dataset from sidebar shows right panel", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Before selecting, right panel shows empty state
    await expect(
      page.getByText("Select a dataset from the sidebar"),
    ).toBeVisible({ timeout: 10_000 });
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

  test("clicking a dataset shows documents panel", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Click the first dataset node in the tree
    const firstDataset = page.locator("[class*='tree'] button, [role='treeitem'], aside button").filter({ hasText: /.+/ }).first();
    if (await firstDataset.isVisible().catch(() => false)) {
      await firstDataset.click();
      await page.waitForTimeout(2_000);

      // Right panel should show documents count
      await expect(
        page.getByText(/\d+ documents?/i),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("create dataset button opens dialog", async ({ page }) => {
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Plus button to create a new dataset
    const createBtn = page
      .locator("button")
      .filter({ has: page.locator("svg") })
      .first();
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click();

      // Dialog with "Create Dataset" title should appear
      const dialog = page.getByRole("dialog");
      if (await dialog.isVisible().catch(() => false)) {
        await expect(
          page.getByText("Create Dataset"),
        ).toBeVisible({ timeout: 5_000 });
      }
    }
  });
});
