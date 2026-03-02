import { test, expect } from "@playwright/test";

test.describe("Case Setup", () => {
  test("claims section shows seeded claims", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show claims from seeding
    const claims = page
      .getByText(/environmental|securities|merger valuation/i)
      .first();
    await expect(claims).toBeVisible({ timeout: 10_000 });
  });

  test("parties section shows seeded parties", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show at least some known party names
    const parties = ["John Reeves", "Lisa Park", "Robert Kim", "Sarah Chen"];
    let found = 0;
    for (const name of parties) {
      if (
        await page
          .getByText(name, { exact: false })
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        found++;
      }
    }
    expect(found).toBeGreaterThanOrEqual(2);
  });

  test("defined terms section shows seeded terms", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Should show defined terms
    const terms = ["Acme", "Pinnacle", "Denver Plant"];
    let found = 0;
    for (const term of terms) {
      if (
        await page
          .getByText(term, { exact: false })
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        found++;
      }
    }
    expect(found).toBeGreaterThanOrEqual(2);
  });
});
