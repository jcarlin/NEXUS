import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());

  await page.getByLabel(/email/i).fill("admin@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: /sign in/i }).click();

  // Wait for redirect to dashboard and page to stabilize
  await expect(page).toHaveURL("/", { timeout: 15_000 });
  await page.waitForLoadState("networkidle");

  // Inject demo matter into the persisted Zustand store
  await page.evaluate(() => {
    const raw = localStorage.getItem("nexus-app-store");
    const store = raw ? JSON.parse(raw) : { state: {} };
    store.state = { ...store.state, matterId: "00000000-0000-0000-0000-000000000001" };
    localStorage.setItem("nexus-app-store", JSON.stringify(store));
  });

  await page.context().storageState({ path: authFile });
});
