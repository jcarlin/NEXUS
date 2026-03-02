import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());

  await page.getByLabel(/email/i).fill("admin@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: /sign in/i }).click();

  // Wait for redirect to dashboard
  await expect(page).toHaveURL("/", { timeout: 15_000 });

  // Wait for matter to be selected (app needs matter context)
  await page.waitForTimeout(2_000);

  await page.context().storageState({ path: authFile });
});
