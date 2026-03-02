import { test, expect } from "@playwright/test";

test.describe("Chat", () => {
  test("shows existing thread in sidebar", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Thread sidebar should show at least 1 seeded thread
    const threadItems = page
      .locator("aside a, aside [role='button'], [class*='thread']")
      .filter({ hasText: /.+/ });
    await expect(threadItems.first()).toBeVisible({ timeout: 10_000 });
  });

  test("clicking thread shows messages", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Click the first thread
    const threadItem = page
      .locator("aside a, aside [role='button'], [class*='thread']")
      .filter({ hasText: /.+/ })
      .first();
    await threadItem.click();
    await page.waitForTimeout(2_000);

    // Should see messages from user and assistant
    const messages = page.locator(
      "[data-testid='assistant-message'], [class*='message']",
    );
    await expect(messages.first()).toBeVisible({ timeout: 10_000 });
  });

  test("can submit a new query", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Type a query
    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("Who is John Reeves?");

    // Submit
    const sendButton = page.getByRole("button", { name: /send|submit|ask/i });
    await sendButton.click();

    // Wait for response (LLM call — generous timeout)
    const response = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{20,}/ });
    await expect(response.first()).toBeVisible({ timeout: 60_000 });
  });
});
