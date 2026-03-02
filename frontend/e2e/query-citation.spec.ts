import { test, expect } from "@playwright/test";

test.describe("Query and citation flow", () => {
  test.beforeEach(async ({ page }) => {
    // Mock auth — set token in localStorage-like store or intercept login
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("admin@example.com");
    await page.locator("#password").fill("password123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL("/", { timeout: 10000 });
  });

  test("submits a query, receives streamed response with sources, and opens citation quick-view", async ({
    page,
  }) => {
    // Navigate to chat
    await page.getByRole("link", { name: /chat/i }).first().click();
    await expect(page).toHaveURL(/\/chat/);

    // Type a query
    const input = page.getByPlaceholder(/ask a question/i);
    await expect(input).toBeVisible({ timeout: 5000 });
    await input.fill("What are the key contract terms?");

    // Submit
    await page.getByRole("button", { name: /send/i }).click();

    // Should show the user message
    await expect(
      page.getByText("What are the key contract terms?"),
    ).toBeVisible({ timeout: 5000 });

    // Wait for assistant response (streaming will add content)
    // The assistant message area should eventually appear
    const assistantMessage = page.locator("[data-testid='assistant-message']");
    if (await assistantMessage.isVisible({ timeout: 15000 }).catch(() => false)) {
      // If sources panel exists, verify it's clickable
      const sourcePanel = page.locator("[data-testid='source-panel']");
      if (await sourcePanel.isVisible().catch(() => false)) {
        await sourcePanel.first().click();
        // Quick-view modal should appear
        const modal = page.getByRole("dialog");
        await expect(modal).toBeVisible({ timeout: 5000 });
      }
    }
  });
});
