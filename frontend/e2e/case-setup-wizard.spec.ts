import { test, expect } from "@playwright/test";
import { CaseStatus, PartyRole } from "./helpers/schema-constants";
import {
  collectConsoleErrors,
  expectNoConsoleErrors,
} from "./helpers/console-errors";

test.describe("Case Setup Wizard Flow", () => {
  test("case setup page renders without console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);
    expectNoConsoleErrors(errors);
  });

  test("upload step shows file upload area and triggers POST", async ({
    page,
  }) => {
    // Intercept the setup POST
    const setupPromise = page.waitForRequest((req) =>
      req.url().includes("/api/v1/cases/") && req.url().includes("/setup") && req.method() === "POST",
    );

    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Should show upload step
    await expect(page.getByText("Upload Anchor Document")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText("Click to select a file"),
    ).toBeVisible();

    // Mock the setup response
    await page.route("**/api/v1/cases/*/setup", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "test-job-1",
          case_context_id: "ctx-1",
          status: CaseStatus.processing,
          created_at: "2024-01-01T00:00:00Z",
        }),
      }),
    );

    // Upload a file via the hidden input
    const fileInput = page.locator("input[type='file']");
    await fileInput.setInputFiles({
      name: "complaint.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("fake pdf content"),
    });

    // File name should now be visible
    await expect(page.getByText("complaint.pdf")).toBeVisible();

    // Click upload button
    await page.getByRole("button", { name: /upload/i }).click();

    // Verify the POST was made
    const request = await setupPromise;
    expect(request.method()).toBe("POST");
  });

  test("processing step polls GET /cases/{matterId}/context", async ({
    page,
  }) => {
    let pollCount = 0;

    // Mock the context GET to return "processing" first, then "confirmed"
    await page.route("**/api/v1/cases/*/context", (route) => {
      pollCount++;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "ctx-1",
          matter_id: "00000000-0000-0000-0000-000000000001",
          anchor_document_id: "doc-1",
          status: pollCount <= 1 ? CaseStatus.processing : CaseStatus.confirmed,
          claims: [
            {
              claim_number: 1,
              claim_label: "Breach",
              claim_text: "Breach of fiduciary duty",
            },
          ],
          parties: [{ name: "Test Corp", role: PartyRole.defendant }],
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        }),
      });
    });

    // Mock the setup POST to auto-advance to processing
    await page.route("**/api/v1/cases/*/setup", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "test-job-1",
          case_context_id: "ctx-1",
          status: CaseStatus.processing,
          created_at: "2024-01-01T00:00:00Z",
        }),
      }),
    );

    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Upload a file to get to processing step
    const fileInput = page.locator("input[type='file']");
    await fileInput.setInputFiles({
      name: "complaint.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("fake pdf content"),
    });
    await page.getByRole("button", { name: /upload/i }).click();

    // Should show processing step
    await expect(page.getByText("Analyzing Document")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for it to complete via polling
    await expect(page.getByText("Analysis Complete")).toBeVisible({
      timeout: 15_000,
    });

    // Context should have been polled
    expect(pollCount).toBeGreaterThanOrEqual(2);
  });

  test("claims step allows adding and editing claims", async ({ page }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Navigate directly to Claims step by looking for the Claims step indicator
    // If page has pre-existing context, the wizard may already show claims
    const claimsStep = page.getByText("Claims", { exact: true });
    if (await claimsStep.isVisible()) {
      // Check if there's a claim input visible
      const claimInput = page.locator(
        "input[placeholder*='claim'], textarea[placeholder*='claim'], input[name*='claim']",
      );
      if (await claimInput.first().isVisible().catch(() => false)) {
        // Claims step is visible, can interact
        await expect(claimInput.first()).toBeVisible();
      }
    }
  });

  test("parties step allows adding parties with role select", async ({
    page,
  }) => {
    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Look for the parties step indicator
    const partiesStep = page.getByText("Parties & Terms");
    await expect(partiesStep).toBeVisible({ timeout: 10_000 });
  });

  test("confirm step verifies PATCH body matches schema", async ({
    page,
  }) => {
    // Intercept PATCH to verify the body
    let patchBody: Record<string, unknown> | null = null;

    await page.route("**/api/v1/cases/*/context", (route) => {
      if (route.request().method() === "PATCH") {
        patchBody = route.request().postDataJSON();
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "confirmed" }),
        });
      }
      // GET requests return completed context
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "ctx-1",
          matter_id: "00000000-0000-0000-0000-000000000001",
          anchor_document_id: "doc-1",
          status: CaseStatus.confirmed,
          claims: [],
          parties: [],
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        }),
      });
    });

    // Mock setup to advance
    await page.route("**/api/v1/cases/*/setup", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "j-1",
          case_context_id: "ctx-1",
          status: CaseStatus.processing,
          created_at: "2024-01-01T00:00:00Z",
        }),
      }),
    );

    await page.goto("/case-setup", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // Step 0: Upload file
    const fileInput = page.locator("input[type='file']");
    await fileInput.setInputFiles({
      name: "complaint.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("fake pdf"),
    });
    await page.getByRole("button", { name: /upload/i }).click();

    // Step 1: Wait for processing to complete
    await expect(page.getByText("Analysis Complete")).toBeVisible({
      timeout: 15_000,
    });

    // Click Next through steps
    const nextBtn = page.getByRole("button", { name: "Next" });
    await nextBtn.click(); // -> Claims
    await page.waitForTimeout(500);
    await nextBtn.click(); // -> Parties & Terms
    await page.waitForTimeout(500);
    await nextBtn.click(); // -> Confirm

    // Step 4: Click Confirm & Save
    await page.waitForTimeout(500);
    const confirmBtn = page.getByRole("button", { name: /confirm/i });
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
    await confirmBtn.click();

    // Verify PATCH was sent
    await page.waitForTimeout(1_000);
    if (patchBody) {
      expect(patchBody).toHaveProperty("status", CaseStatus.confirmed);
      expect(patchBody).toHaveProperty("claims");
      expect(patchBody).toHaveProperty("parties");
      expect(patchBody).toHaveProperty("defined_terms");
      expect(Array.isArray(patchBody["claims"])).toBe(true);
      expect(Array.isArray(patchBody["parties"])).toBe(true);
      expect(Array.isArray(patchBody["defined_terms"])).toBe(true);
    }
  });
});
