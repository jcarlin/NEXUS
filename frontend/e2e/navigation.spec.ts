import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("sidebar links are present and clickable", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Core sidebar navigation links
    const navLinks = [
      { text: /dashboard/i, url: "/" },
      { text: /chat/i, url: "/chat" },
      { text: /documents/i, url: "/documents" },
      { text: /entities/i, url: "/entities" },
    ];

    for (const { text } of navLinks) {
      const link = page
        .locator("nav a, aside a")
        .filter({ hasText: text })
        .first();
      await expect(link).toBeVisible({ timeout: 5_000 });
    }
  });

  test("matter selector shows a matter name", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Matter selector should show some matter name (not empty)
    const matterSelector = page.locator("header button, nav button")
      .filter({ hasText: /.{3,}/ })
      .first();
    await expect(matterSelector).toBeVisible({ timeout: 10_000 });
  });

  test("command palette opens with keyboard shortcut", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Open command palette
    await page.keyboard.press("Meta+k");

    // Should see command palette dialog/modal
    const palette = page.getByPlaceholder(/command|search/i).first();
    await expect(palette).toBeVisible({ timeout: 5_000 });

    // Close it
    await page.keyboard.press("Escape");
  });

  test("no error boundaries on sequential navigation", async ({ page }) => {
    test.setTimeout(90_000);
    const routes = [
      "/",
      "/chat",
      "/documents",
      "/entities",
      "/datasets",
      "/analytics/comms",
      "/analytics/timeline",
      "/entities/network",
      "/review/hot-docs",
      "/review/result-set",
      "/case-setup",
      "/admin/users",
      "/admin/audit-log",
      "/admin/evaluation",
    ];

    for (const route of routes) {
      await page.goto(route, { waitUntil: "domcontentloaded", timeout: 10_000 }).catch(() => {});
      await page.waitForTimeout(500);

      const errorBoundary = page.locator("[data-testid='error-boundary']");
      const isError = await errorBoundary.isVisible().catch(() => false);
      expect(isError, `Error boundary visible on ${route}`).toBe(false);
    }
  });
});
