import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Knowledge Graph", () => {
  test("page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("heading is visible", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    await expect(
      page.getByRole("heading", { name: "Knowledge Graph" }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("graph health card shows total nodes > 0", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    await expect(page.getByText("Total Nodes")).toBeVisible({
      timeout: 10_000,
    });

    // The count next to "Total Nodes" should be a number > 0
    const nodesCard = page
      .locator(":has(> :text('Total Nodes'))")
      .first();
    const text = await nodesCard.textContent();
    const match = text?.match(/(\d+)/);
    expect(match).not.toBeNull();
    expect(Number(match![1])).toBeGreaterThan(0);
  });

  test("graph health card shows total edges > 0", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    await expect(page.getByText("Total Edges")).toBeVisible({
      timeout: 10_000,
    });

    const edgesCard = page
      .locator(":has(> :text('Total Edges'))")
      .first();
    const text = await edgesCard.textContent();
    const match = text?.match(/(\d+)/);
    expect(match).not.toBeNull();
    expect(Number(match![1])).toBeGreaterThan(0);
  });

  test("node type badges render", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    // At least one node type badge should be visible (Document, Entity, Chunk, Email, etc.)
    const nodeTypes = [
      "Document",
      "Entity",
      "Chunk",
      "Email",
      "person",
      "organization",
      "location",
    ];
    let found = false;
    for (const type of nodeTypes) {
      if (
        await page
          .getByText(type, { exact: false })
          .first()
          .isVisible({ timeout: 5_000 })
          .catch(() => false)
      ) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test("document table renders", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    // Table with document columns should be visible
    const table = page.locator("table").first();
    await expect(table).toBeVisible({ timeout: 10_000 });

    // Should have expected column headers
    await expect(
      page.getByText(/Filename|Document/i).first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText(/Entities/i).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("document rows have data", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("Neo4j status badges visible", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    // "Indexed" or "Missing" badges should appear in the document table
    const indexed = page.getByText("Indexed").first();
    const missing = page.getByText("Missing").first();

    const indexedVisible = await indexed.isVisible().catch(() => false);
    const missingVisible = await missing.isVisible().catch(() => false);
    expect(indexedVisible || missingVisible).toBe(true);
  });

  test("reprocess buttons exist", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    const reprocessAll = page.getByRole("button", {
      name: /Re-process All Unprocessed/i,
    });
    const resolveEntities = page.getByRole("button", {
      name: /Resolve Entities/i,
    });
    const resolveAgent = page.getByRole("button", {
      name: /Resolve \(Agent\)/i,
    });

    await expect(reprocessAll).toBeVisible({ timeout: 10_000 });
    await expect(resolveEntities).toBeVisible({ timeout: 10_000 });
    await expect(resolveAgent).toBeVisible({ timeout: 10_000 });
  });

  test("select-all checkbox toggles selection", async ({ page }) => {
    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2_000);

    // Wait for table rows to load
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Find the select-all checkbox in the table header
    const selectAll = page
      .locator("table thead input[type='checkbox'], table thead [role='checkbox']")
      .first();
    await expect(selectAll).toBeVisible({ timeout: 10_000 });

    await selectAll.click();
    await page.waitForTimeout(500);

    // Row checkboxes should now be checked
    const rowCheckboxes = page.locator(
      "table tbody input[type='checkbox'], table tbody [role='checkbox']",
    );
    const firstCheckbox = rowCheckboxes.first();
    await expect(firstCheckbox).toBeVisible();

    // Check the checked state (works for both native and aria checkboxes)
    const isChecked =
      (await firstCheckbox.isChecked().catch(() => false)) ||
      (await firstCheckbox
        .getAttribute("data-state")
        .then((s) => s === "checked")
        .catch(() => false));
    expect(isChecked).toBe(true);
  });

  test("no API 5xx errors", async ({ page }) => {
    const apiErrors: string[] = [];

    page.on("response", (response) => {
      const url = response.url();
      if (url.includes("/api/") && response.status() >= 500) {
        apiErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto("/admin/knowledge-graph", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(5_000);

    if (apiErrors.length > 0) {
      throw new Error(
        `API 5xx errors detected:\n${apiErrors.map((e) => `  • ${e}`).join("\n")}`,
      );
    }
  });
});
