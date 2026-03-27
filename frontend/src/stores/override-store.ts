import { create } from "zustand";
import { persist } from "zustand/middleware";

export type OverrideValue = boolean | number;
export const EMPTY_OVERRIDES: Record<string, OverrideValue> = {};

interface OverrideStore {
  threadOverrides: Record<string, Record<string, OverrideValue>>;
  setOverride: (threadId: string, flag: string, value: OverrideValue | null) => void;
  getOverrides: (threadId: string) => Record<string, OverrideValue>;
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
