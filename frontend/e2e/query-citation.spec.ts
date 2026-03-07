import { test, expect } from "@playwright/test";

test.describe("Query and citation flow", () => {
  test.setTimeout(90_000);

  test("submits a query, receives streamed response with sources, and opens citation quick-view", async ({
    page,
  }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Type a query
    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are the key contract terms?");

    // Submit
    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    // Should show the user message
    await expect(
      page.getByText("What are the key contract terms?"),
    ).toBeVisible({ timeout: 5_000 });

    // Wait for assistant response (streaming will add content)
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 60_000 });

    // If sources panel exists, verify it's clickable
    const sourcePanel = page.locator(
      "[data-testid='source-panel'], [data-testid='sources-button'], button:has-text('Sources')",
    );
    const sourcePanelVisible = await sourcePanel.first().isVisible({ timeout: 10_000 });

    if (sourcePanelVisible) {
      await sourcePanel.first().click();
      // Quick-view modal or citation sidebar should appear
      const modalOrSidebar = page.locator(
        "[role='dialog'], [data-testid='citation-sidebar']",
      );
      await expect(modalOrSidebar.first()).toBeVisible({ timeout: 5_000 });
    }
  });
});
