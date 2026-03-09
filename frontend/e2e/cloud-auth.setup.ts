import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/cloud-user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());

  await page
    .getByLabel(/email/i)
    .fill(process.env.E2E_EMAIL || "admin@nexus-demo.com");
  await page
    .locator("#password")
    .fill(process.env.E2E_PASSWORD || "nexus-demo-2026");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page).toHaveURL("/", { timeout: 15_000 });
  await page.waitForLoadState("networkidle");

  await page.evaluate(() => {
    const raw = localStorage.getItem("nexus-app-store");
    const store = raw ? JSON.parse(raw) : { state: {} };
    store.state = {
      ...store.state,
      matterId: "00000000-0000-0000-0000-000000000001",
    };
    localStorage.setItem("nexus-app-store", JSON.stringify(store));
  });

  await page.context().storageState({ path: authFile });
});
