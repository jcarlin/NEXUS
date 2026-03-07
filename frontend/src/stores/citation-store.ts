import { create } from "zustand";
import type { SourceDocument, CitedClaim } from "@/types";

interface CitationSidebarState {
  isOpen: boolean;
  activeSource: SourceDocument | null;
  allSources: SourceDocument[];
  allClaims: CitedClaim[];
  mode: "compact" | "expanded";

  openWithSources: (
    sources: SourceDocument[],
    claims: CitedClaim[],
    activeSource?: SourceDocument,
  ) => void;
  setActiveSource: (source: SourceDocument) => void;
  expandView: () => void;
  collapseView: () => void;
  toggle: () => void;
  close: () => void;
}

export const useCitationStore = create<CitationSidebarState>()((set) => ({
  isOpen: false,
  activeSource: null,
  allSources: [],
  allClaims: [],
  mode: "compact",

  openWithSources: (sources, claims, activeSource) =>
    set({
      isOpen: true,
      allSources: sources,
      allClaims: claims,
      activeSource: activeSource ?? sources[0] ?? null,
    }),

  setActiveSource: (source) => set({ activeSource: source }),

  expandView: () => set({ mode: "expanded" }),

  collapseView: () => set({ mode: "compact" }),

  toggle: () =>
    set((state) => ({
      isOpen: state.allSources.length > 0 ? !state.isOpen : false,
    })),

  close: () =>
    set({
      isOpen: false,
      activeSource: null,
      allSources: [],
      allClaims: [],
      mode: "compact",
    }),
}));
