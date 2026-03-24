import { create } from "zustand";
import { persist } from "zustand/middleware";

const MAX_MATTERS = 10;

interface ViewStateData {
  states: Record<string, Record<string, Record<string, unknown>>>;
  /** Tracks MRU order for pruning. Most recent at end. */
  mru: string[];
}

interface ViewStateActions {
  getPageState: <T extends Record<string, unknown>>(
    matterId: string,
    pageKey: string,
  ) => T | undefined;
  setPageState: <T extends Record<string, unknown>>(
    matterId: string,
    pageKey: string,
    patch: Partial<T>,
  ) => void;
  clearMatter: (matterId: string) => void;
  clearAll: () => void;
}

type ViewStateStore = ViewStateData & ViewStateActions;

function touchMru(mru: string[], matterId: string): string[] {
  const filtered = mru.filter((id) => id !== matterId);
  filtered.push(matterId);
  return filtered;
}

function pruneMatters(
  states: ViewStateData["states"],
  mru: string[],
): { states: ViewStateData["states"]; mru: string[] } {
  if (mru.length <= MAX_MATTERS) return { states, mru };
  const toRemove = mru.slice(0, mru.length - MAX_MATTERS);
  const nextStates = { ...states };
  for (const id of toRemove) {
    delete nextStates[id];
  }
  return { states: nextStates, mru: mru.slice(-MAX_MATTERS) };
}

export const useViewStateStore = create<ViewStateStore>()(
  persist(
    (set, get) => ({
      states: {},
      mru: [],

      getPageState: <T extends Record<string, unknown>>(
        matterId: string,
        pageKey: string,
      ): T | undefined => {
        const matterState = get().states[matterId];
        if (!matterState) return undefined;
        return matterState[pageKey] as T | undefined;
      },

      setPageState: <T extends Record<string, unknown>>(
        matterId: string,
        pageKey: string,
        patch: Partial<T>,
      ) => {
        set((state) => {
          const matterState = state.states[matterId] ?? {};
          const pageState = matterState[pageKey] ?? {};
          const updatedMru = touchMru(state.mru, matterId);
          const merged = {
            states: {
              ...state.states,
              [matterId]: {
                ...matterState,
                [pageKey]: { ...pageState, ...patch },
              },
            },
            mru: updatedMru,
          };
          return pruneMatters(merged.states, merged.mru);
        });
      },

      clearMatter: (matterId: string) => {
        set((state) => {
          const nextStates = { ...state.states };
          delete nextStates[matterId];
          return {
            states: nextStates,
            mru: state.mru.filter((id) => id !== matterId),
          };
        });
      },

      clearAll: () => {
        set({ states: {}, mru: [] });
      },
    }),
    {
      name: "nexus-view-state",
      version: 1,
      partialize: (state) => ({
        states: state.states,
        mru: state.mru,
      }),
    },
  ),
);
