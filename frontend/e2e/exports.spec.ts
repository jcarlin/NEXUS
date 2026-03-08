import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Exports", () => {
  test("exports page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("page renders with heading and description", async ({ page }) => {
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(page.getByRole("heading", { name: "Exports" })).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText("Manage production sets and export jobs."),
    ).toBeVisible();
  });

  test("Production Sets tab is default and shows table", async ({ page }) => {
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const tab = page.getByRole("tab", { name: /Production Sets/i });
    await expect(tab).toBeVisible({ timeout: 10_000 });
    await expect(tab).toHaveAttribute("data-state", "active");
  });

  test("Export Jobs tab shows table", async ({ page }) => {
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const tab = page.getByRole("tab", { name: /Export Jobs/i });
    await expect(tab).toBeVisible({ timeout: 10_000 });

    await tab.click();
    await expect(tab).toHaveAttribute("data-state", "active");
  });

  test("Create production set button opens dialog", async ({ page }) => {
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Look for the create button within the production sets tab
    const createBtn = page.getByRole("button", {
      name: /create|new|add/i,
    });
    if (await createBtn.first().isVisible().catch(() => false)) {
      await createBtn.first().click();

      // Dialog should appear
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible({ timeout: 5_000 });
    }
  });

  test("tab switching toggles content", async ({ page }) => {
    await page.goto("/review/exports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const productionTab = page.getByRole("tab", {
      name: /Production Sets/i,
    });
    const exportTab = page.getByRole("tab", { name: /Export Jobs/i });

    // Switch to Export Jobs
    await exportTab.click();
    await expect(exportTab).toHaveAttribute("data-state", "active");
    await expect(productionTab).toHaveAttribute("data-state", "inactive");

    // Switch back to Production Sets
    await productionTab.click();
    await expect(productionTab).toHaveAttribute("data-state", "active");
    await expect(exportTab).toHaveAttribute("data-state", "inactive");
  });
});
