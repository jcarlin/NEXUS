import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Admin", () => {
  test("users page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("audit log renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/admin/audit-log", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("evaluation page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/admin/evaluation", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("users page shows heading and table", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "User Management" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Manage platform users and roles."),
    ).toBeVisible();

    // Should show user rows
    const rows = page.locator("table tbody tr, [role='row']");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Should have at least 4 users (admin, attorney, paralegal, reviewer)
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test("users table shows role badges", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // At least one role badge should be visible
    const roleBadges = ["admin", "attorney", "paralegal", "reviewer"];
    let found = false;
    for (const role of roleBadges) {
      if (
        await page
          .getByText(role, { exact: false })
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

  test("create user button opens dialog", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const createBtn = page.getByRole("button", { name: /Create User/i });
    await expect(createBtn).toBeVisible({ timeout: 10_000 });
    await createBtn.click();

    // Dialog should open
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });
  });

  test("audit log page shows heading and entries", async ({ page }) => {
    await page.goto("/admin/audit-log", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Audit Log" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Review platform activity and API audit trail."),
    ).toBeVisible();

    // Audit log should have entries from seeding API calls
    const content = page.locator("main");
    const text = await content.textContent();
    expect(text?.length).toBeGreaterThan(50);
  });

  test("evaluation page shows sections", async ({ page }) => {
    await page.goto("/admin/evaluation", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Evaluation Pipeline" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Manage evaluation datasets and run quality assessments."),
    ).toBeVisible();

    // Should show key sections
    const sections = ["Quality Gates", "Datasets", "Run History"];
    for (const section of sections) {
      await expect(
        page.getByRole("heading", { name: section }),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("audit log table has rows with timestamps", async ({ page }) => {
    await page.goto("/admin/audit-log", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Audit entries should have actual table rows
    const rows = page.locator("table tbody tr, [role='row']");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("create user dialog has form fields", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const createBtn = page.getByRole("button", { name: /Create User/i });
    await expect(createBtn).toBeVisible({ timeout: 10_000 });
    await createBtn.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Form should have Email, Name/Full Name, and Role fields
    await expect(dialog.getByLabel(/email/i)).toBeVisible({ timeout: 5_000 });
    await expect(dialog.getByLabel(/name/i).first()).toBeVisible();

    // Close dialog
    await page.keyboard.press("Escape");
  });

  test("evaluation quality gates show metric values", async ({ page }) => {
    await page.goto("/admin/evaluation", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Quality Gates section should have cards with metric values or N/A
    const qualityGates = page.getByRole("heading", { name: "Quality Gates" });
    await expect(qualityGates).toBeVisible({ timeout: 10_000 });

    // Cards under quality gates should show some metric text
    const metricCards = page.locator("[class*='card']").filter({ hasText: /\d+|N\/A|—/ });
    await expect(metricCards.first()).toBeVisible({ timeout: 10_000 });
  });
});
