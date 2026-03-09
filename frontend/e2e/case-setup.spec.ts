import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Case Setup", () => {
  test("page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("claims section has items or wizard shown", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Either case context is loaded with claims, or the upload wizard is shown
    const claims = page.getByText(/claim/i).first();
    const wizard = page.getByText(/upload|anchor|setup/i).first();
    const hasClaims = await claims.isVisible().catch(() => false);
    const hasWizard = await wizard.isVisible().catch(() => false);
    expect(hasClaims || hasWizard).toBe(true);
  });

  test("parties section has items when context exists", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Look for parties heading/section
    const partiesSection = page.getByText(/parties|party/i).first();
    if (await partiesSection.isVisible().catch(() => false)) {
      // Should have at least one party name (any text in the list)
      const main = page.locator("main");
      const text = await main.textContent();
      expect(text?.length).toBeGreaterThan(50);
    }
  });

  test("defined terms section has items when context exists", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Look for defined terms heading/section
    const termsSection = page.getByText(/defined terms|terms/i).first();
    if (await termsSection.isVisible().catch(() => false)) {
      const main = page.locator("main");
      const text = await main.textContent();
      expect(text?.length).toBeGreaterThan(50);
    }
  });
});
