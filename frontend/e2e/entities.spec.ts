import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Entities", () => {
  test("entity list renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("network graph renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/entities/network", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(5_000);
    expectNoConsoleErrors(errors);
  });

  test("entity list shows extracted entities", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Should have entity rows
    const rows = page.locator(
      "table tbody tr, [role='row'], [class*='entity']",
    );
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(5);
  });

  test("entity rows have name and type", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(5);

    // First row should have non-empty name text
    const firstRowText = await rows.first().textContent();
    expect(firstRowText?.trim().length).toBeGreaterThan(0);

    // Type badges should be visible (person, organization, location, etc.)
    const typeBadge = page.locator("table tbody tr td span, table tbody tr td div, table tbody tr td [class*='badge']")
      .filter({ hasText: /person|organization|location|date|monetary|email|phone|geo|event/i })
      .first();
    await expect(typeBadge).toBeVisible({ timeout: 15_000 });
  });

  test("entity detail page shows connections", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Click first entity
    const firstEntity = page
      .locator(
        "table tbody tr a, [role='row'] a, [class*='entity'] a",
      )
      .first();
    if (await firstEntity.isVisible().catch(() => false)) {
      await firstEntity.click();
      await expect(page).toHaveURL(/\/entities\//, { timeout: 10_000 });
      await page.waitForTimeout(2_000);

      // Detail page should render
      const content = page.locator("main, [class*='content']");
      await expect(content).toBeVisible();
    }
  });

  test("network graph page renders", async ({ page }) => {
    await page.goto("/entities/network", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Graph should render as canvas or SVG
    const graph = page
      .locator("canvas, svg, [class*='graph'], [class*='network']")
      .first();
    await expect(graph).toBeVisible({ timeout: 15_000 });
  });

  test("entity detail shows connections graph", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstEntity = page
      .locator("table tbody tr a, [role='row'] a, [class*='entity'] a")
      .first();
    if (await firstEntity.isVisible().catch(() => false)) {
      await firstEntity.click();
      await expect(page).toHaveURL(/\/entities\//, { timeout: 10_000 });
      await page.waitForTimeout(3_000);

      // Should have a connections graph (canvas or SVG)
      const graph = page
        .locator("canvas, svg, [class*='graph'], [class*='connection']")
        .first();
      await expect(graph).toBeVisible({ timeout: 15_000 });
    }
  });

  test("entity detail shows document mentions section", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstEntity = page
      .locator("table tbody tr a, [role='row'] a, [class*='entity'] a")
      .first();
    if (await firstEntity.isVisible().catch(() => false)) {
      await firstEntity.click();
      await expect(page).toHaveURL(/\/entities\//, { timeout: 10_000 });
      await page.waitForTimeout(3_000);

      // Document mentions section should be present
      const mentions = page.getByText(/document|mention/i).first();
      await expect(mentions).toBeVisible({ timeout: 10_000 });
    }
  });

  test("network graph page shows heading and description", async ({
    page,
  }) => {
    await page.goto("/entities/network", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    await expect(
      page.getByRole("heading", { name: "Network Graph" }),
    ).toBeVisible({ timeout: 10_000 });

    // Description should show entity/connection counts
    await expect(page.getByText(/entities.*connections|connections/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("network graph has back link", async ({ page }) => {
    await page.goto("/entities/network", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // "Back" is rendered as a link, not a button
    const backLink = page.getByRole("link", { name: /back/i });
    await expect(backLink).toBeVisible({ timeout: 10_000 });
  });

  test("entity detail has back to entities link", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const firstEntity = page
      .locator("table tbody tr a, [role='row'] a, [class*='entity'] a")
      .first();
    if (await firstEntity.isVisible().catch(() => false)) {
      await firstEntity.click();
      await expect(page).toHaveURL(/\/entities\//, { timeout: 10_000 });
      await page.waitForTimeout(2_000);

      await expect(
        page.getByText("Back to Entities"),
      ).toBeVisible({ timeout: 10_000 });
    }
  });
});
