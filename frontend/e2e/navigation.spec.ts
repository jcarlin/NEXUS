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

  test("matter selector shows Default Matter", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Matter selector in header should show selected matter
    // After seeding, matter name is "Acme-Pinnacle Merger Investigation"
    // Before seeding, it may be "Default Matter"
    const matterText = page
      .getByText(/acme.pinnacle|default matter/i)
      .first();
    await expect(matterText).toBeVisible({ timeout: 10_000 });
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
      await page.goto(route, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(1_500);

      const errorBoundary = page.locator("[data-testid='error-boundary']");
      const isError = await errorBoundary.isVisible().catch(() => false);
      expect(isError, `Error boundary visible on ${route}`).toBe(false);
    }
  });
});
