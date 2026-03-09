import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Chat", () => {
  test("chat page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

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

  test("thread detail shows message history", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Click the first thread link (href contains /chat/)
    const threadLink = page.locator("aside a[href*='/chat/']").first();
    if (await threadLink.isVisible().catch(() => false)) {
      await threadLink.click();
      await expect(page).toHaveURL(/\/chat\//, { timeout: 10_000 });
      await page.waitForTimeout(2_000);

      // Should show messages from assistant
      const messages = page.locator(
        "[data-testid='assistant-message'], [class*='message']",
      );
      await expect(messages.first()).toBeVisible({ timeout: 10_000 });
    }
  });

  test("new chat has empty input ready", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Message input should be present and empty
    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await expect(input).toHaveValue("");
  });

  test("message input has send button", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const sendButton = page.getByRole("button", { name: /send|submit|ask/i });
    await expect(sendButton).toBeVisible({ timeout: 10_000 });
  });

  test("no API errors during query submission", async ({ page }) => {
    const apiErrors: string[] = [];
    page.on("response", (res) => {
      if (res.url().includes("/api/") && res.status() >= 500) {
        apiErrors.push(`${res.status()} ${res.url()}`);
      }
    });

    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    if (await input.isVisible().catch(() => false)) {
      await input.fill("What documents are in this matter?");
      const sendButton = page.getByRole("button", { name: /send|submit|ask/i });
      if (await sendButton.isVisible().catch(() => false)) {
        await sendButton.click();
        await page.waitForTimeout(10_000);
        expect(apiErrors.length, `API 5xx errors: ${apiErrors.join(", ")}`).toBe(0);
      }
    }
  });
});
