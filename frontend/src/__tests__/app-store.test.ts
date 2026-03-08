import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "@/stores/app-store";
import type { CitedClaim } from "@/types";

const makeClaim = (text: string): CitedClaim => ({
  claim: text,
  source_id: `src-${text}`,
  filename: `${text}.pdf`,
  page: 1,
  quote: `Quote for ${text}`,
  verified: true,
});

describe("useAppStore", () => {
  beforeEach(() => {
    const store = useAppStore.getState();
    store.clearFindings();
    store.setSidebarCollapsed(false);
    store.setThreadSidebarCollapsed(false);
    // Reset matter and dataset
    useAppStore.setState({ matterId: null, datasetId: null, definedTermsOpen: false });
  });

  describe("matter and dataset", () => {
    it("setMatter() sets matterId and clears datasetId", () => {
      useAppStore.setState({ datasetId: "ds-1" });
      useAppStore.getState().setMatter("matter-123");

      const state = useAppStore.getState();
      expect(state.matterId).toBe("matter-123");
      expect(state.datasetId).toBeNull();
    });

    it("setDataset() sets datasetId", () => {
      useAppStore.getState().setDataset("ds-42");
      expect(useAppStore.getState().datasetId).toBe("ds-42");
    });

    it("setDataset(null) clears datasetId", () => {
      useAppStore.getState().setDataset("ds-42");
      useAppStore.getState().setDataset(null);
      expect(useAppStore.getState().datasetId).toBeNull();
    });

    it("setMatter() overrides previous matter", () => {
      useAppStore.getState().setMatter("matter-1");
      useAppStore.getState().setMatter("matter-2");
      expect(useAppStore.getState().matterId).toBe("matter-2");
    });
  });

  describe("findings", () => {
    it("addFinding() appends to findings array", () => {
      const claim = makeClaim("test");
      useAppStore.getState().addFinding(claim);

      const findings = useAppStore.getState().findings;
      expect(findings).toHaveLength(1);
      expect(findings[0]!.claim).toBe("test");
    });

    it("addFinding() appends multiple findings", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));
      useAppStore.getState().addFinding(makeClaim("c"));

      expect(useAppStore.getState().findings).toHaveLength(3);
    });

    it("removeFinding(index) removes by index", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));
      useAppStore.getState().addFinding(makeClaim("c"));

      useAppStore.getState().removeFinding(1);

      const findings = useAppStore.getState().findings;
      expect(findings).toHaveLength(2);
      expect(findings[0]!.claim).toBe("a");
      expect(findings[1]!.claim).toBe("c");
    });

    it("removeFinding() with first index removes first item", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));

      useAppStore.getState().removeFinding(0);
      expect(useAppStore.getState().findings).toHaveLength(1);
      expect(useAppStore.getState().findings[0]!.claim).toBe("b");
    });

    it("reorderFindings(from, to) moves item correctly", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));
      useAppStore.getState().addFinding(makeClaim("c"));

      useAppStore.getState().reorderFindings(0, 2);

      const findings = useAppStore.getState().findings;
      expect(findings[0]!.claim).toBe("b");
      expect(findings[1]!.claim).toBe("c");
      expect(findings[2]!.claim).toBe("a");
    });

    it("reorderFindings() moving item backward", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));
      useAppStore.getState().addFinding(makeClaim("c"));

      useAppStore.getState().reorderFindings(2, 0);

      const findings = useAppStore.getState().findings;
      expect(findings[0]!.claim).toBe("c");
      expect(findings[1]!.claim).toBe("a");
      expect(findings[2]!.claim).toBe("b");
    });

    it("clearFindings() empties array", () => {
      useAppStore.getState().addFinding(makeClaim("a"));
      useAppStore.getState().addFinding(makeClaim("b"));
      useAppStore.getState().clearFindings();

      expect(useAppStore.getState().findings).toHaveLength(0);
    });

    it("clearFindings() on empty array is a no-op", () => {
      useAppStore.getState().clearFindings();
      expect(useAppStore.getState().findings).toHaveLength(0);
    });
  });

  describe("sidebar state", () => {
    it("toggleSidebar() toggles sidebarCollapsed", () => {
      expect(useAppStore.getState().sidebarCollapsed).toBe(false);
      useAppStore.getState().toggleSidebar();
      expect(useAppStore.getState().sidebarCollapsed).toBe(true);
      useAppStore.getState().toggleSidebar();
      expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    });

    it("setSidebarCollapsed() sets exact value", () => {
      useAppStore.getState().setSidebarCollapsed(true);
      expect(useAppStore.getState().sidebarCollapsed).toBe(true);
      useAppStore.getState().setSidebarCollapsed(false);
      expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    });

    it("toggleThreadSidebar() toggles threadSidebarCollapsed", () => {
      expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);
      useAppStore.getState().toggleThreadSidebar();
      expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);
      useAppStore.getState().toggleThreadSidebar();
      expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);
    });

    it("setThreadSidebarCollapsed() sets exact value", () => {
      useAppStore.getState().setThreadSidebarCollapsed(true);
      expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);
      useAppStore.getState().setThreadSidebarCollapsed(false);
      expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);
    });

    it("toggleDefinedTerms() toggles definedTermsOpen", () => {
      expect(useAppStore.getState().definedTermsOpen).toBe(false);
      useAppStore.getState().toggleDefinedTerms();
      expect(useAppStore.getState().definedTermsOpen).toBe(true);
      useAppStore.getState().toggleDefinedTerms();
      expect(useAppStore.getState().definedTermsOpen).toBe(false);
    });
  });
});
