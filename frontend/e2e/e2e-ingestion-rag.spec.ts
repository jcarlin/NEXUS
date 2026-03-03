import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API = "http://localhost:8000/api/v1";

test.describe.serial("E2E: Ingest document → RAG query", () => {
  // Shared state across sequential tests
  let authToken: string;
  let matterId: string;
  let jobId: string;
  let documentId: string;
  let datasetId: string;

  /** Build headers with auth + matter scope for API calls. */
  function apiHeaders(extra?: Record<string, string>) {
    return {
      Authorization: `Bearer ${authToken}`,
      "X-Matter-ID": matterId,
      ...extra,
    };
  }

  test("upload document via API", async ({ page }) => {
    // Login to get auth token
    const loginResp = await page.request.post(`${API}/auth/login`, {
      data: { email: "admin@example.com", password: "password123" },
    });
    expect(loginResp.ok()).toBeTruthy();
    const loginData = await loginResp.json();
    authToken = loginData.access_token;
    expect(authToken).toBeTruthy();

    // Fetch the user's first matter
    const mattersResp = await page.request.get(`${API}/auth/me/matters`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(mattersResp.ok()).toBeTruthy();
    const matters = await mattersResp.json();
    expect(matters.length).toBeGreaterThan(0);
    matterId = matters[0].id;

    // Read the test fixture file
    const fixturePath = path.resolve(__dirname, "fixtures/test-contract.txt");
    const fileBuffer = fs.readFileSync(fixturePath);

    // Upload via multipart POST /ingest
    const ingestResp = await page.request.post(`${API}/ingest`, {
      headers: apiHeaders(),
      multipart: {
        file: {
          name: "test-contract.txt",
          mimeType: "text/plain",
          buffer: fileBuffer,
        },
      },
    });
    expect(ingestResp.ok()).toBeTruthy();

    const ingestData = await ingestResp.json();
    expect(ingestData.job_id).toBeTruthy();
    expect(ingestData.filename).toBe("test-contract.txt");
    jobId = ingestData.job_id;
  });

  test("poll job until processing completes", async ({ page }) => {
    test.setTimeout(130_000);

    let status = "pending";
    const deadline = Date.now() + 120_000;

    while (status !== "complete" && Date.now() < deadline) {
      await page.waitForTimeout(3_000);

      const resp = await page.request.get(`${API}/jobs/${jobId}`, {
        headers: apiHeaders(),
      });
      expect(resp.ok()).toBeTruthy();

      const data = await resp.json();
      status = data.status;

      // Fail fast if the job errored out
      if (status === "failed") {
        throw new Error(`Job failed: ${data.error || "unknown error"}`);
      }
    }

    expect(status).toBe("complete");
  });

  test("verify document appears in documents list", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2_000);

    // The uploaded filename should appear in the documents table
    const filenameCell = page.getByText("test-contract.txt", { exact: false });
    await expect(filenameCell.first()).toBeVisible({ timeout: 10_000 });

    // Click into the document row to verify navigation works
    await filenameCell.first().click();
    await expect(page).toHaveURL(/\/documents\//, { timeout: 10_000 });
  });

  test("create dataset and assign document", async ({ page }) => {
    // Look up the document ID via API
    const docsResp = await page.request.get(
      `${API}/documents?q=test-contract.txt`,
      { headers: apiHeaders() },
    );
    expect(docsResp.ok()).toBeTruthy();
    const docsData = await docsResp.json();
    expect(docsData.items.length).toBeGreaterThan(0);
    documentId = docsData.items[0].id;

    // Create dataset via API
    const dsResp = await page.request.post(`${API}/datasets`, {
      headers: apiHeaders({ "Content-Type": "application/json" }),
      data: { name: "E2E Test Dataset", description: "Created by E2E test" },
    });
    expect(dsResp.status()).toBe(201);
    const dsData = await dsResp.json();
    datasetId = dsData.id;
    expect(datasetId).toBeTruthy();

    // Assign document to dataset
    const assignResp = await page.request.post(
      `${API}/datasets/${datasetId}/documents`,
      {
        headers: apiHeaders({ "Content-Type": "application/json" }),
        data: { document_ids: [documentId] },
      },
    );
    expect(assignResp.ok()).toBeTruthy();

    // Verify dataset is visible in the UI
    await page.goto("/datasets", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    const datasetName = page.getByText("E2E Test Dataset", { exact: false });
    await expect(datasetName.first()).toBeVisible({ timeout: 10_000 });
  });

  test("query via RAG returns assistant response", async ({ page }) => {
    test.setTimeout(120_000);

    // Submit the query via the API directly (avoids SSE streaming timing issues)
    const streamResp = await page.request.post(`${API}/query/stream`, {
      headers: apiHeaders({ "Content-Type": "application/json" }),
      data: {
        query:
          "What is the purchase price in the Meridian Holdings contract?",
      },
    });
    expect(streamResp.ok()).toBeTruthy();
    const streamBody = await streamResp.text();

    // Parse the SSE response to extract the thread_id from the done event.
    // SSE lines may be separated by \n or \r\n; Playwright may also collapse them.
    const doneMatch =
      streamBody.match(/event:\s*done[\r\n]+data:\s*(.+)/) ??
      streamBody.match(/"thread_id"\s*:\s*"([^"]+)"/);
    expect(doneMatch).toBeTruthy();

    let threadId: string;
    try {
      const doneData = JSON.parse(doneMatch![1]);
      threadId = doneData.thread_id;
    } catch {
      // Fallback: the second regex captured the thread_id directly
      threadId = doneMatch![1];
    }
    expect(threadId).toBeTruthy();

    // Navigate to the thread detail page to see persisted messages
    await page.goto(`/chat/${threadId}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3_000);

    // Verify both the user question and assistant response are displayed
    const assistantMsg = page.locator("[data-testid='assistant-message']");
    await expect(assistantMsg.first()).toBeVisible({ timeout: 15_000 });

    // Verify the assistant actually produced some text
    const msgText = await assistantMsg.first().textContent();
    expect(msgText).toBeTruthy();
    expect(msgText!.length).toBeGreaterThan(10);
  });

  test("verify Qdrant embeddings exist", async ({ page }) => {
    // Query Qdrant directly for collection info
    const qdrantResp = await page.request.get(
      "http://localhost:6333/collections/nexus_text",
    );
    expect(qdrantResp.ok()).toBeTruthy();

    const qdrantData = await qdrantResp.json();
    const collectionInfo = qdrantData.result;

    // Verify vector size matches nomic-embed-text (768 dimensions)
    const vectorSize =
      collectionInfo.config?.params?.vectors?.dense?.size ??
      collectionInfo.config?.params?.vectors?.size;
    expect(vectorSize).toBe(768);

    // Verify at least some points have been indexed
    expect(collectionInfo.points_count).toBeGreaterThan(0);
  });
});
