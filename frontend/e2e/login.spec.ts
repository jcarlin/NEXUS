import { test, expect } from "@playwright/test";

test.describe("Login flow", () => {
  test("redirects unauthenticated user to login and renders dashboard after login", async ({
    page,
  }) => {
    // Clear persisted auth state so we start unauthenticated
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());

    // Navigate to root — should redirect to /login
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);

    // Login page should show the form
    await expect(page.getByText("NEXUS", { exact: true })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();

    // Fill in credentials and submit
    await page.getByLabel(/email/i).fill("admin@example.com");
    await page.locator("#password").fill("password123");
    await page.getByRole("button", { name: /sign in/i }).click();

    // After login, should redirect to dashboard
    await expect(page).toHaveURL("/", { timeout: 10000 });
    await expect(
      page.getByRole("heading", { name: /dashboard/i }),
    ).toBeVisible();
  });
});
