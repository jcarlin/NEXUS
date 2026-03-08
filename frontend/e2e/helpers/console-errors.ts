import type { Page } from "@playwright/test";

/**
 * Collect browser console errors during a page visit.
 *
 * Usage:
 *   const errors = collectConsoleErrors(page);
 *   // … interact with page …
 *   expectNoConsoleErrors(errors);
 */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore known noisy errors that are not actionable
      if (
        text.includes("Failed to load resource") ||
        text.includes("net::ERR_") ||
        text.includes("favicon.ico")
      ) {
        return;
      }
      errors.push(text);
    }
  });
  return errors;
}

/**
 * Assert that no unexpected console errors were logged.
 * Call this at the end of a test after all interactions.
 */
export function expectNoConsoleErrors(errors: string[]) {
  if (errors.length > 0) {
    throw new Error(
      `Browser console errors detected:\n${errors.map((e) => `  • ${e}`).join("\n")}`,
    );
  }
}
