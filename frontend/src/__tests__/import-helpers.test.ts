import { describe, it, expect } from "vitest";
import {
  buildProcessUploadedPayload,
  calculateIngestProgress,
} from "@/lib/import-helpers";

describe("buildProcessUploadedPayload", () => {
  it("transforms camelCase to snake_case", () => {
    const result = buildProcessUploadedPayload([
      { objectKey: "raw/abc/doc.pdf", filename: "doc.pdf" },
    ]);
    expect(result).toEqual({
      files: [{ object_key: "raw/abc/doc.pdf", filename: "doc.pdf" }],
    });
  });

  it("handles multiple files", () => {
    const result = buildProcessUploadedPayload([
      { objectKey: "raw/1/a.pdf", filename: "a.pdf" },
      { objectKey: "raw/2/b.pdf", filename: "b.pdf" },
    ]);
    expect(result.files).toHaveLength(2);
  });

  it("filters out files with empty objectKey", () => {
    const result = buildProcessUploadedPayload([
      { objectKey: "raw/1/a.pdf", filename: "a.pdf" },
      { objectKey: "", filename: "bad.pdf" },
    ]);
    expect(result.files).toHaveLength(1);
    expect(result.files[0]!.filename).toBe("a.pdf");
  });

  it("returns empty files array when all filtered out", () => {
    const result = buildProcessUploadedPayload([
      { objectKey: "", filename: "bad.pdf" },
    ]);
    expect(result.files).toEqual([]);
  });
});

describe("calculateIngestProgress", () => {
  it("returns 0 when total is 0", () => {
    expect(
      calculateIngestProgress({
        processed_documents: 0,
        failed_documents: 0,
        skipped_documents: 0,
        total_documents: 0,
      }),
    ).toBe(0);
  });

  it("returns 100 when all processed", () => {
    expect(
      calculateIngestProgress({
        processed_documents: 10,
        failed_documents: 0,
        skipped_documents: 0,
        total_documents: 10,
      }),
    ).toBe(100);
  });

  it("includes failed and skipped in progress", () => {
    expect(
      calculateIngestProgress({
        processed_documents: 5,
        failed_documents: 2,
        skipped_documents: 3,
        total_documents: 20,
      }),
    ).toBe(50);
  });

  it("rounds to nearest integer", () => {
    expect(
      calculateIngestProgress({
        processed_documents: 1,
        failed_documents: 0,
        skipped_documents: 0,
        total_documents: 3,
      }),
    ).toBe(33);
  });
});
