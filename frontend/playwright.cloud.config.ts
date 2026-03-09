import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 2,
  workers: 1,
  timeout: 120_000,
  reporter: "html",
  use: {
    baseURL:
      process.env.CLOUD_URL || "https://nexus-alpha-swart.vercel.app",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "cloud-setup", testMatch: /cloud-auth\.setup\.ts/ },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/cloud-user.json",
      },
      dependencies: ["cloud-setup"],
    },
  ],
});
