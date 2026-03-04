import { describe, it, expect } from "vitest";
import { ingestSchema } from "@/components/datasets/ingest-form";

describe("ingestSchema validation", () => {
  it("accepts valid directory input", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "directory",
      source_path: "/data/documents/",
      resume: false,
      disable_hnsw: false,
    });
    expect(result.success).toBe(true);
  });

  it("accepts all adapter types", () => {
    const adapters = [
      "directory",
      "huggingface_csv",
      "edrm_xml",
      "concordance_dat",
    ];
    for (const adapter of adapters) {
      const result = ingestSchema.safeParse({
        adapter_type: adapter,
        source_path: "/data/test",
      });
      expect(result.success).toBe(true);
    }
  });

  it("rejects empty source_path", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "directory",
      source_path: "",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]!.path).toContain("source_path");
    }
  });

  it("rejects invalid adapter_type", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "invalid",
      source_path: "/data/test",
    });
    expect(result.success).toBe(false);
  });

  it("accepts optional limit as positive integer", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "directory",
      source_path: "/data/test",
      limit: 100,
    });
    expect(result.success).toBe(true);
  });

  it("rejects negative limit", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "directory",
      source_path: "/data/test",
      limit: -1,
    });
    expect(result.success).toBe(false);
  });

  it("accepts optional content_dir", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "edrm_xml",
      source_path: "/data/loadfile.xml",
      content_dir: "/data/files/",
    });
    expect(result.success).toBe(true);
  });

  it("defaults resume and disable_hnsw to false", () => {
    const result = ingestSchema.safeParse({
      adapter_type: "directory",
      source_path: "/data/test",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.resume).toBe(false);
      expect(result.data.disable_hnsw).toBe(false);
    }
  });
});
