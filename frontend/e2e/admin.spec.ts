import { test, expect } from "@playwright/test";

test.describe("Admin", () => {
  test("users table shows seeded users", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Should show user rows
    const rows = page.locator("table tbody tr, [role='row']");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Should have at least 4 users (admin, attorney, paralegal, reviewer)
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(4);
  });

  test("audit log shows entries", async ({ page }) => {
    await page.goto("/admin/audit-log", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Audit log should have entries from seeding API calls
    const content = page.locator("main");
    await expect(content).toBeVisible();

    // Should have some text content (entries)
    const text = await content.textContent();
    expect(text?.length).toBeGreaterThan(50);
  });

  test("evaluation page shows completed run", async ({ page }) => {
    await page.goto("/admin/evaluation", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Should show evaluation metrics or run info
    const content = page.locator("main");
    await expect(content).toBeVisible();

    // Look for metric values or "completed" status
    const metricsOrRun = page
      .getByText(/faithfulness|relevance|completed|accuracy/i)
      .first();
    await expect(metricsOrRun).toBeVisible({ timeout: 10_000 });
  });
});
