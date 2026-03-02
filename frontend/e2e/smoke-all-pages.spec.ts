import { test, expect, type Page } from "@playwright/test";

/**
 * Smoke test: navigate every page in the app, capture console errors and
 * failed network requests.  Produces a summary at the end.
 */

const CREDENTIALS = {
  email: "admin@example.com",
  password: "password123",
};

// Every authenticated route we expect to reach
const PAGES: { path: string; label: string; heading?: RegExp }[] = [
  { path: "/", label: "Dashboard", heading: /dashboard/i },
  { path: "/chat", label: "Chat" },
  { path: "/documents", label: "Documents", heading: /documents/i },
  { path: "/documents/import", label: "Import" },
  { path: "/entities", label: "Entities", heading: /entities/i },
  { path: "/entities/network", label: "Network Graph" },
  { path: "/analytics/comms", label: "Comms Matrix" },
  { path: "/analytics/timeline", label: "Timeline" },
  { path: "/review/hot-docs", label: "Hot Docs" },
  { path: "/review/result-set", label: "Result Set" },
  { path: "/datasets", label: "Datasets" },
  { path: "/case-setup", label: "Case Setup" },
  { path: "/admin/users", label: "Admin Users" },
  { path: "/admin/audit-log", label: "Audit Log" },
  { path: "/admin/evaluation", label: "Evaluation" },
];

type PageError = {
  page: string;
  type: "console" | "network" | "render";
  message: string;
};

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(CREDENTIALS.email);
  await page.locator("#password").fill(CREDENTIALS.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Wait for redirect to dashboard
  await expect(page).toHaveURL("/", { timeout: 15000 });
}

test.describe("Smoke test: all pages", () => {
  test.setTimeout(120_000);
  const errors: PageError[] = [];

  test("login and navigate every page", async ({ page }) => {
    // ---- 1. Login ----
    await login(page);
    await expect(
      page.getByRole("heading", { name: /dashboard/i }),
    ).toBeVisible({ timeout: 10000 });

    // ---- 2. Visit every page ----
    for (const entry of PAGES) {
      // Collect console errors and failed network requests per page
      const pageConsoleErrors: string[] = [];
      const pageNetworkErrors: string[] = [];

      const onConsole = (msg: import("@playwright/test").ConsoleMessage) => {
        if (msg.type() === "error") {
          pageConsoleErrors.push(msg.text());
        }
      };
      const onResponse = (res: import("@playwright/test").Response) => {
        const url = res.url();
        // Only track API errors, not static assets
        if (res.status() >= 400 && url.includes("/api/")) {
          pageNetworkErrors.push(`${res.status()} ${url}`);
        }
      };

      page.on("console", onConsole);
      page.on("response", onResponse);

      try {
        await page.goto(entry.path, { waitUntil: "domcontentloaded", timeout: 15000 });
        // Give React time to render
        await page.waitForTimeout(2000);

        // Check for uncaught error boundaries / crash screens
        const errorBoundary = page.locator(
          '[data-testid="error-boundary"], .error-boundary, text="Something went wrong"',
        );
        if (await errorBoundary.isVisible({ timeout: 1000 }).catch(() => false)) {
          errors.push({
            page: entry.label,
            type: "render",
            message: "Error boundary rendered (page crash)",
          });
        }

        // If the page has a known heading, verify it
        if (entry.heading) {
          const headingVisible = await page
            .getByRole("heading", { name: entry.heading })
            .isVisible({ timeout: 5000 })
            .catch(() => false);
          if (!headingVisible) {
            errors.push({
              page: entry.label,
              type: "render",
              message: `Expected heading matching ${entry.heading} not found`,
            });
          }
        }
      } catch (err) {
        errors.push({
          page: entry.label,
          type: "render",
          message: `Navigation failed: ${(err as Error).message}`,
        });
      }

      // Record collected errors
      for (const msg of pageConsoleErrors) {
        errors.push({ page: entry.label, type: "console", message: msg });
      }
      for (const msg of pageNetworkErrors) {
        errors.push({ page: entry.label, type: "network", message: msg });
      }

      page.removeListener("console", onConsole);
      page.removeListener("response", onResponse);
    }

    // ---- 3. Summary ----
    if (errors.length > 0) {
      const summary = errors
        .map((e) => `[${e.type.toUpperCase()}] ${e.page}: ${e.message}`)
        .join("\n");

      console.log("\n========== ERROR SUMMARY ==========");
      console.log(`Total issues: ${errors.length}`);
      console.log(summary);
      console.log("===================================\n");

      // Attach as test annotation so it shows in the HTML report
      test.info().annotations.push({
        type: "error-summary",
        description: summary,
      });
    } else {
      console.log("\nAll pages loaded cleanly with no errors.\n");
    }

    // Fail the test if there are render errors (page crashes / missing headings)
    const renderErrors = errors.filter((e) => e.type === "render");
    if (renderErrors.length > 0) {
      const msg = renderErrors
        .map((e) => `${e.page}: ${e.message}`)
        .join("\n");
      expect.soft(renderErrors.length, `Render errors found:\n${msg}`).toBe(0);
    }
  });
});
