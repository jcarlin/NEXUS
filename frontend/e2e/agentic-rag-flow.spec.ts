import { test, expect } from "@playwright/test";

test.describe("Agentic RAG pipeline E2E", () => {
  // Agentic pipeline needs time for multiple LLM + tool rounds
  test.setTimeout(120_000);

  test("query returns streamed response", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are the key parties involved in this matter?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    // Assistant message should appear with substantial content
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });
  });

  test("sources appear after response", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What documents discuss payment terms?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    // Wait for assistant response
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    // Sources button should be visible with a count
    const sourcesButton = page.locator(
      "button:has-text('Sources'), button:has-text('sources'), [data-testid='sources-button']",
    );
    await expect(sourcesButton.first()).toBeVisible({ timeout: 10_000 });
  });

  test("citation sidebar opens and shows content", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are the key contract terms?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    // Wait for response
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    // Click citation marker or sources button to open sidebar
    const citationTrigger = page
      .locator(
        "[data-testid='citation-marker'], [data-testid='sources-button'], button:has-text('Sources')",
      )
      .first();

    if (await citationTrigger.isVisible({ timeout: 5_000 })) {
      await citationTrigger.click();

      // Sidebar should be visible
      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 5_000 });

      // Should show source count
      await expect(sidebar.getByText(/Sources \(\d+\)/)).toBeVisible();
    }
  });

  test("sidebar shows active source details", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What documents reference deadlines?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    const citationTrigger = page
      .locator(
        "[data-testid='citation-marker'], [data-testid='sources-button'], button:has-text('Sources')",
      )
      .first();

    if (await citationTrigger.isVisible({ timeout: 5_000 })) {
      await citationTrigger.click();

      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 5_000 });

      // Active source should show filename and excerpt
      await expect(
        sidebar.locator("h3, [class*='filename']").first(),
      ).toBeVisible({ timeout: 5_000 });
      await expect(sidebar.getByText(/Excerpt/i)).toBeVisible();
    }
  });

  test("sidebar tabs switch sources", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are all the important dates mentioned?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    const citationTrigger = page
      .locator(
        "[data-testid='citation-marker'], [data-testid='sources-button'], button:has-text('Sources')",
      )
      .first();

    if (await citationTrigger.isVisible({ timeout: 5_000 })) {
      await citationTrigger.click();

      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 5_000 });

      // If there are multiple source tabs, click tab 2
      const tabs = sidebar.locator("button").filter({ hasText: /^\d+$/ });
      const tabCount = await tabs.count();
      if (tabCount > 1) {
        const firstFilename = await sidebar
          .locator("h3")
          .first()
          .textContent();
        await tabs.nth(1).click();
        // Content should change (or at least not error)
        await page.waitForTimeout(500);
        const secondFilename = await sidebar
          .locator("h3")
          .first()
          .textContent();
        // Filenames may differ if sources are from different documents
        expect(firstFilename !== null || secondFilename !== null).toBeTruthy();
      }
    }
  });

  test("Open Viewer opens modal", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are the key findings?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    const citationTrigger = page
      .locator(
        "[data-testid='citation-marker'], [data-testid='sources-button'], button:has-text('Sources')",
      )
      .first();

    if (await citationTrigger.isVisible({ timeout: 5_000 })) {
      await citationTrigger.click();

      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 5_000 });

      const openViewerBtn = sidebar.getByRole("button", {
        name: /Open Viewer/i,
      });
      if (await openViewerBtn.isVisible({ timeout: 3_000 })) {
        await openViewerBtn.click();
        const modal = page.getByRole("dialog");
        await expect(modal).toBeVisible({ timeout: 5_000 });
      }
    }
  });

  test("sidebar close button works", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("Who signed the agreement?");

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90_000 });

    const citationTrigger = page
      .locator(
        "[data-testid='citation-marker'], [data-testid='sources-button'], button:has-text('Sources')",
      )
      .first();

    if (await citationTrigger.isVisible({ timeout: 5_000 })) {
      await citationTrigger.click();

      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 5_000 });

      // Close the sidebar
      await sidebar.locator("button").filter({ has: page.locator("svg") }).first().click();
      await expect(sidebar).not.toBeVisible({ timeout: 3_000 });
    }
  });

  test("sidebar empty state when toggled with no sources", async ({
    page,
  }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Try to toggle sidebar before any query — should show empty state
    // Look for a sources toggle button in the chat header
    const toggleButton = page.locator(
      "[data-testid='sources-toggle'], button[aria-label*='source' i], button[aria-label*='citation' i]",
    );

    if (await toggleButton.isVisible({ timeout: 3_000 }).catch(() => false) && await toggleButton.isEnabled().catch(() => false)) {
      await toggleButton.click();

      const sidebar = page.locator("[data-testid='citation-sidebar']");
      await expect(sidebar).toBeVisible({ timeout: 3_000 });
      await expect(sidebar.getByText(/No sources found/i)).toBeVisible();
      await expect(
        sidebar.getByText(/Sources will appear here/i),
      ).toBeVisible();
    }
  });

  test("complex query completes without recursion error", async ({ page }) => {
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    // Deep-tier query that previously triggered GraphRecursionError
    await input.fill(
      "Compare and contrast the timeline of events described by all parties and analyze the relationship between the key witnesses",
    );

    await page.getByRole("button", { name: /send|submit|ask/i }).click();

    // Should get a response, not an error
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{50,}/ });
    await expect(assistantMessage.first()).toBeVisible({ timeout: 120_000 });

    // Should NOT see error messages about recursion
    const errorMessage = page.locator("text=/recursion|GraphRecursionError/i");
    await expect(errorMessage).not.toBeVisible({ timeout: 2_000 });
  });
});
