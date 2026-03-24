import { useCallback } from "react";
import { useAppStore } from "@/stores/app-store";
import { useViewStateStore } from "@/stores/view-state-store";

/**
 * JSON-serializable sorting state (mirrors TanStack Table's SortingState).
 * Defined here to avoid coupling the store to @tanstack/react-table.
 */
export type SortingEntry = { id: string; desc: boolean };

export interface ViewStateMap {
  "/documents": {
    search: string;
    fileExtension: string;
    offset: number;
    sorting: SortingEntry[];
  };
  "/entities": {
    search: string;
    entityType: string;
    offset: number;
    sorting: SortingEntry[];
  };
  "/review/result-set": {
    offset: number;
    sorting: SortingEntry[];
    globalFilter: string;
  };
  "/review/hot-docs": {
    sorting: SortingEntry[];
    globalFilter: string;
  };
  "/review/exports": {
    activeTab: string;
    psOffset: number;
    jobOffset: number;
  };
  "/admin/audit-log": {
    sorting: SortingEntry[];
    globalFilter: string;
  };
  "/admin/users": {
    sorting: SortingEntry[];
    globalFilter: string;
  };
  "/entities/network": {
    activeTypes: string[];
  };
  "/analytics/timeline": {
    entity: string;
    startDate: string;
    endDate: string;
  };
  "/analytics/comms": {
    activeTab: string;
  };
  "/admin/architecture": {
    activeTab: string;
  };
  "/datasets": {
    selectedId: string | null;
    docOffset: number;
  };
}

/**
 * Persists page-level view state (filters, sorting, pagination, tabs)
 * across navigation, scoped per matter.
 *
 * Returns a `[state, patchSetter]` tuple similar to `useState`.
 * The setter shallow-merges the patch into the persisted state.
 *
 * When `matterId` is null or no persisted state exists, returns `defaults`.
 */
export function useViewState<K extends keyof ViewStateMap>(
  pageKey: K,
  defaults: ViewStateMap[K],
): [ViewStateMap[K], (patch: Partial<ViewStateMap[K]>) => void] {
  const matterId = useAppStore((s) => s.matterId);
  // Subscribe to the actual states object so the hook re-renders on store writes.
  const statesObj = useViewStateStore((s) => s.states);
  const setPageState = useViewStateStore((s) => s.setPageState);

  const persisted =
    matterId && statesObj[matterId]?.[pageKey]
      ? (statesObj[matterId][pageKey] as Partial<ViewStateMap[K]>)
      : undefined;

  // Merge persisted over defaults so any new keys added to defaults
  // are present even if the persisted state is from an older schema.
  const state: ViewStateMap[K] = persisted
    ? { ...defaults, ...persisted }
    : defaults;

  const setter = useCallback(
    (patch: Partial<ViewStateMap[K]>) => {
      if (!matterId) return;
      setPageState(matterId, pageKey, patch);
    },
    [matterId, pageKey, setPageState],
  );

  return [state, setter];
}
