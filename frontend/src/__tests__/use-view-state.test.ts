import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useViewState } from "@/hooks/use-view-state";
import { useAppStore } from "@/stores/app-store";
import { useViewStateStore } from "@/stores/view-state-store";

const DEFAULTS = { search: "", offset: 0 } as const;

describe("useViewState", () => {
  beforeEach(() => {
    useViewStateStore.getState().clearAll();
    useAppStore.setState({ matterId: "m1" });
  });

  it("returns defaults when no persisted state exists", () => {
    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );
    expect(result.current[0]).toEqual({
      search: "",
      fileExtension: "all",
      offset: 0,
      sorting: [],
    });
  });

  it("returns defaults when matterId is null", () => {
    useAppStore.setState({ matterId: null });

    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );
    expect(result.current[0]).toEqual({
      search: "",
      fileExtension: "all",
      offset: 0,
      sorting: [],
    });
  });

  it("setter does nothing when matterId is null", () => {
    useAppStore.setState({ matterId: null });

    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );

    act(() => {
      result.current[1]({ search: "test" });
    });

    // Store should remain empty
    expect(useViewStateStore.getState().states).toEqual({});
  });

  it("persists state via setter and returns it", () => {
    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );

    act(() => {
      result.current[1]({ search: "contract", offset: 50 });
    });

    expect(result.current[0].search).toBe("contract");
    expect(result.current[0].offset).toBe(50);
    expect(result.current[0].fileExtension).toBe("all"); // untouched field
  });

  it("shallow-merges patches (does not replace entire state)", () => {
    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );

    act(() => {
      result.current[1]({ search: "hello" });
    });
    act(() => {
      result.current[1]({ offset: 100 });
    });

    expect(result.current[0].search).toBe("hello");
    expect(result.current[0].offset).toBe(100);
  });

  it("returns correct state after matter switch", () => {
    // Set state for m1
    useViewStateStore
      .getState()
      .setPageState("m1", "/documents", { search: "alpha" });
    // Set state for m2
    useViewStateStore
      .getState()
      .setPageState("m2", "/documents", { search: "beta" });

    const { result, rerender } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );

    expect(result.current[0].search).toBe("alpha");

    // Switch matter
    act(() => {
      useAppStore.setState({ matterId: "m2" });
    });
    rerender();

    expect(result.current[0].search).toBe("beta");
  });

  it("merges persisted state over defaults (new keys from defaults survive)", () => {
    // Simulate persisted state from older schema (missing fileExtension)
    useViewStateStore
      .getState()
      .setPageState("m1", "/documents", { search: "old", offset: 25 });

    const { result } = renderHook(() =>
      useViewState("/documents", { search: "", fileExtension: "all", offset: 0, sorting: [] }),
    );

    // Persisted values win
    expect(result.current[0].search).toBe("old");
    expect(result.current[0].offset).toBe(25);
    // New default key is present
    expect(result.current[0].fileExtension).toBe("all");
  });
});
