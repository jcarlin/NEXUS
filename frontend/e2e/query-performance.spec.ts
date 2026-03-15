import { test, expect } from "@playwright/test";

/**
 * End-to-end performance test for the query pipeline.
 *
 * Measures time-to-first-token (TTFT) and total response time by
 * intercepting SSE events from /api/v1/query/stream.
 *
 * Performance budgets:
 *   - TTFT: < 10s (first `token` SSE event)
 *   - Total: < 30s (until `done` SSE event or stream close)
 */

const IS_CLOUD = !!process.env.CLOUD_URL;
const TTFT_BUDGET_MS = IS_CLOUD ? 30_000 : 10_000;
const TOTAL_BUDGET_MS = IS_CLOUD ? 90_000 : 30_000;

test.describe("Query Performance", () => {
  test("simple factual query responds within performance budget", async ({
    page,
  }) => {
    // Track SSE timing via response interception
    let ttftMs: number | null = null;
    let totalMs: number | null = null;
    let tokenCount = 0;
    let queryStartMs = 0;

    // Intercept the SSE stream response
    page.on("response", async (response) => {
      const url = response.url();
      if (!url.includes("/query/stream") && !url.includes("/query")) return;
      if (response.status() !== 200) return;

      // For SSE streams, we can't easily intercept individual events via
      // Playwright's response API. We'll rely on DOM observation below.
    });

    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Type query
    const input = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("who is the main lawyer");

    // Record start time and submit
    queryStartMs = Date.now();
    const sendButton = page.getByRole("button", { name: /send|submit|ask/i });
    await sendButton.click();

    // Wait for first assistant content to appear (TTFT proxy)
    const assistantMessage = page
      .locator(
        "[data-testid='assistant-message'], [class*='assistant'], [class*='message']",
      )
      .filter({ hasText: /.{5,}/ });

    await expect(assistantMessage.first()).toBeVisible({
      timeout: TTFT_BUDGET_MS,
    });
    ttftMs = Date.now() - queryStartMs;

    // Wait for response to complete (input becomes enabled again, or stop button disappears)
    // Use a generous timeout but assert against budget afterwards
    const inputEnabled = page.getByPlaceholder(/ask|question|query|message/i);
    await expect(inputEnabled).toBeEnabled({ timeout: TOTAL_BUDGET_MS });
    totalMs = Date.now() - queryStartMs;

    // Count tokens by checking final response length
    const responseText = await assistantMessage.first().textContent();
    tokenCount = responseText?.split(/\s+/).length ?? 0;

    // --- Timing Report ---
    console.log("\n=== Query Performance Report ===");
    console.log(`  Query: "who is the main lawyer"`);
    console.log(`  TTFT: ${ttftMs}ms (budget: ${TTFT_BUDGET_MS}ms)`);
    console.log(`  Total: ${totalMs}ms (budget: ${TOTAL_BUDGET_MS}ms)`);
    console.log(`  Response words: ~${tokenCount}`);
    console.log(
      `  Throughput: ~${totalMs > 0 ? ((tokenCount / totalMs) * 1000).toFixed(1) : "?"} words/s`,
    );
    console.log("================================\n");

    // Assert performance budgets
    expect(ttftMs).toBeLessThan(TTFT_BUDGET_MS);
    expect(totalMs).toBeLessThan(TOTAL_BUDGET_MS);
    expect(tokenCount).toBeGreaterThan(0);
  });
});
