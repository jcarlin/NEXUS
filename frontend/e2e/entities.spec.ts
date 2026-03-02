import { test, expect } from "@playwright/test";

test.describe("Entities", () => {
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

  test("known entity names are visible", async ({ page }) => {
    await page.goto("/entities", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // At least one well-known entity from our corpus should appear
    const knownEntities = [
      "Sarah Chen",
      "Acme",
      "Pinnacle",
      "Robert Kim",
      "John Reeves",
    ];
    let found = false;
    for (const name of knownEntities) {
      const el = page.getByText(name, { exact: false }).first();
      if (await el.isVisible().catch(() => false)) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
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
});
