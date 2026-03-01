import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CitedClaim } from "@/types";

interface AppState {
  matterId: string | null;
  datasetId: string | null;
  findings: CitedClaim[];
  sidebarCollapsed: boolean;
  definedTermsOpen: boolean;

  setMatter: (matterId: string) => void;
  setDataset: (datasetId: string | null) => void;
  addFinding: (claim: CitedClaim) => void;
  removeFinding: (index: number) => void;
  reorderFindings: (from: number, to: number) => void;
  clearFindings: () => void;
  toggleSidebar: () => void;
  toggleDefinedTerms: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      matterId: null,
      datasetId: null,
      findings: [],
      sidebarCollapsed: false,
      definedTermsOpen: false,

      setMatter: (matterId) => set({ matterId, datasetId: null }),
      setDataset: (datasetId) => set({ datasetId }),

      addFinding: (claim) =>
        set((state) => ({ findings: [...state.findings, claim] })),

      removeFinding: (index) =>
        set((state) => ({
          findings: state.findings.filter((_, i) => i !== index),
        })),

      reorderFindings: (from, to) =>
        set((state) => {
          const findings = [...state.findings];
          const [item] = findings.splice(from, 1);
          if (item) findings.splice(to, 0, item);
          return { findings };
        }),

      clearFindings: () => set({ findings: [] }),
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      toggleDefinedTerms: () =>
        set((state) => ({ definedTermsOpen: !state.definedTermsOpen })),
    }),
    {
      name: "nexus-app-store",
      partialize: (state) => ({
        matterId: state.matterId,
        datasetId: state.datasetId,
        findings: state.findings,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    },
  ),
);
