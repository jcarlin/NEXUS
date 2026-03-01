import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "@/stores/app-store";

describe("app store", () => {
  beforeEach(() => {
    useAppStore.getState().clearFindings();
    useAppStore.setState({ matterId: null, sidebarCollapsed: false });
  });

  it("persists matter selection", () => {
    useAppStore.getState().setMatter("matter-123");
    expect(useAppStore.getState().matterId).toBe("matter-123");
  });

  it("findings accumulate and persist", () => {
    const claim = {
      claim_text: "Test claim",
      document_id: "doc-1",
      filename: "test.pdf",
      page_number: 1,
      bates_range: null,
      excerpt: "excerpt",
      grounding_score: 0.9,
      verification_status: "verified" as const,
    };
    useAppStore.getState().addFinding(claim);
    useAppStore.getState().addFinding({ ...claim, claim_text: "Second claim" });
    expect(useAppStore.getState().findings).toHaveLength(2);
    expect(useAppStore.getState().findings[0]?.claim_text).toBe("Test claim");
  });
});
