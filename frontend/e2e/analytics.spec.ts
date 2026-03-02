import { test, expect } from "@playwright/test";

test.describe("Analytics", () => {
  test("comms matrix renders with data", async ({ page }) => {
    await page.goto("/analytics/comms", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show a table/grid with communication pairs
    const content = page
      .locator(
        "table, [class*='matrix'], [class*='grid'], [class*='heatmap']",
      )
      .first();
    await expect(content).toBeVisible({ timeout: 10_000 });
  });

  test("comms matrix shows sender/recipient names", async ({ page }) => {
    await page.goto("/analytics/comms", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should contain at least one known name
    const names = [
      "Sarah Chen",
      "Robert Kim",
      "Lisa Park",
      "Michael Torres",
    ];
    let found = false;
    for (const name of names) {
      if (
        await page
          .getByText(name, { exact: false })
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test("timeline page renders", async ({ page }) => {
    await page.goto("/analytics/timeline", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Timeline should render with events or search interface
    const content = page.locator("main").first();
    await expect(content).toBeVisible();

    // Should have content, not be an empty page
    const text = await content.textContent();
    expect(text?.length).toBeGreaterThan(10);
  });
});
