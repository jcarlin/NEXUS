import { create } from "zustand";
import { persist } from "zustand/middleware";

export const EMPTY_OVERRIDES: Record<string, boolean> = {};

interface OverrideStore {
  threadOverrides: Record<string, Record<string, boolean>>;
  setOverride: (threadId: string, flag: string, value: boolean | null) => void;
  getOverrides: (threadId: string) => Record<string, boolean>;
  clearOverrides: (threadId: string) => void;
}

export const useOverrideStore = create<OverrideStore>()(
  persist(
    (set, get) => ({
      threadOverrides: {},

      setOverride: (threadId, flag, value) => {
        set((state) => {
          const current = { ...state.threadOverrides[threadId] };
          if (value === null) {
            delete current[flag];
          } else {
            current[flag] = value;
          }
          // Remove the thread entry entirely if no overrides remain
          const next = { ...state.threadOverrides };
          if (Object.keys(current).length === 0) {
            delete next[threadId];
          } else {
            next[threadId] = current;
          }
          return { threadOverrides: next };
        });
      },

      getOverrides: (threadId) => {
        return get().threadOverrides[threadId] ?? {};
      },

      clearOverrides: (threadId) => {
        set((state) => {
          const next = { ...state.threadOverrides };
          delete next[threadId];
          return { threadOverrides: next };
        });
      },
    }),
    {
      name: "nexus-retrieval-overrides",
      partialize: (state) => ({
        threadOverrides: state.threadOverrides,
      }),
    },
  ),
);
