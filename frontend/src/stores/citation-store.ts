import { create } from "zustand";
import type { SourceDocument, CitedClaim } from "@/types";

interface CitationSidebarState {
  isOpen: boolean;
  activeSource: SourceDocument | null;
  allSources: SourceDocument[];
  allClaims: CitedClaim[];

  openWithSources: (
    sources: SourceDocument[],
    claims: CitedClaim[],
    activeSource?: SourceDocument,
  ) => void;
  setActiveSource: (source: SourceDocument) => void;
  toggle: () => void;
  close: () => void;
}

export const useCitationStore = create<CitationSidebarState>()((set) => ({
  isOpen: false,
  activeSource: null,
  allSources: [],
  allClaims: [],

  openWithSources: (sources, claims, activeSource) =>
    set({
      isOpen: true,
      allSources: sources,
      allClaims: claims,
      activeSource: activeSource ?? sources[0] ?? null,
    }),

  setActiveSource: (source) => set({ activeSource: source }),

  toggle: () => set((state) => ({ isOpen: !state.isOpen })),

  close: () =>
    set({
      isOpen: false,
      activeSource: null,
      allSources: [],
      allClaims: [],
    }),
}));
