import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Analytics", () => {
  test("comms page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/analytics/comms", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("timeline page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/analytics/timeline", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

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

  test("comms page has Matrix and Email Threads tabs", async ({ page }) => {
    await page.goto("/analytics/comms", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Communication Analysis" }),
    ).toBeVisible({ timeout: 10_000 });

    const matrixTab = page.getByRole("tab", { name: /Matrix/i });
    const threadsTab = page.getByRole("tab", { name: /Email Threads/i });

    await expect(matrixTab).toBeVisible();
    await expect(threadsTab).toBeVisible();
  });

  test("email threads tab shows thread list", async ({ page }) => {
    await page.goto("/analytics/comms", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const threadsTab = page.getByRole("tab", { name: /Email Threads/i });
    await expect(threadsTab).toBeVisible({ timeout: 10_000 });
    await threadsTab.click();
    await page.waitForTimeout(2_000);

    // Thread table should show expected columns
    await expect(page.getByText("Thread ID")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Subject")).toBeVisible();
    await expect(page.getByText("Messages")).toBeVisible();
  });

  test("timeline page has date range controls", async ({ page }) => {
    await page.goto("/analytics/timeline", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Timeline" }),
    ).toBeVisible({ timeout: 10_000 });

    // Date range inputs should be present
    const entityInput = page.locator("#entity-name");
    await expect(entityInput).toBeVisible({ timeout: 10_000 });

    const startDate = page.locator("#start-date");
    const endDate = page.locator("#end-date");
    await expect(startDate).toBeVisible();
    await expect(endDate).toBeVisible();
  });
});
