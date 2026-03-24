import { describe, it, expect, beforeEach } from "vitest";
import { useViewStateStore } from "@/stores/view-state-store";

describe("useViewStateStore", () => {
  beforeEach(() => {
    useViewStateStore.getState().clearAll();
  });

  describe("getPageState / setPageState", () => {
    it("returns undefined when no state exists", () => {
      const result = useViewStateStore
        .getState()
        .getPageState("m1", "/documents");
      expect(result).toBeUndefined();
    });

    it("stores and retrieves page state", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "test", offset: 50 });

      const result = useViewStateStore
        .getState()
        .getPageState<{ search: string; offset: number }>("m1", "/documents");
      expect(result).toEqual({ search: "test", offset: 50 });
    });

    it("shallow-merges partial updates", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "test", offset: 50 });
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { offset: 100 });

      const result = useViewStateStore
        .getState()
        .getPageState<{ search: string; offset: number }>("m1", "/documents");
      expect(result).toEqual({ search: "test", offset: 100 });
    });

    it("keeps different pages isolated within same matter", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "doc" });
      useViewStateStore
        .getState()
        .setPageState("m1", "/entities", { search: "ent" });

      expect(
        useViewStateStore
          .getState()
          .getPageState<{ search: string }>("m1", "/documents"),
      ).toEqual({ search: "doc" });
      expect(
        useViewStateStore
          .getState()
          .getPageState<{ search: string }>("m1", "/entities"),
      ).toEqual({ search: "ent" });
    });
  });

  describe("matter isolation", () => {
    it("different matters have independent state", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "alpha" });
      useViewStateStore
        .getState()
        .setPageState("m2", "/documents", { search: "beta" });

      expect(
        useViewStateStore
          .getState()
          .getPageState<{ search: string }>("m1", "/documents"),
      ).toEqual({ search: "alpha" });
      expect(
        useViewStateStore
          .getState()
          .getPageState<{ search: string }>("m2", "/documents"),
      ).toEqual({ search: "beta" });
    });
  });

  describe("clearMatter", () => {
    it("removes all state for a matter", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "test" });
      useViewStateStore
        .getState()
        .setPageState("m1", "/entities", { search: "ent" });

      useViewStateStore.getState().clearMatter("m1");

      expect(
        useViewStateStore.getState().getPageState("m1", "/documents"),
      ).toBeUndefined();
      expect(
        useViewStateStore.getState().getPageState("m1", "/entities"),
      ).toBeUndefined();
    });

    it("does not affect other matters", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "a" });
      useViewStateStore
        .getState()
        .setPageState("m2", "/documents", { search: "b" });

      useViewStateStore.getState().clearMatter("m1");

      expect(
        useViewStateStore
          .getState()
          .getPageState<{ search: string }>("m2", "/documents"),
      ).toEqual({ search: "b" });
    });

    it("removes matter from MRU", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "a" });
      useViewStateStore.getState().clearMatter("m1");

      expect(useViewStateStore.getState().mru).not.toContain("m1");
    });
  });

  describe("clearAll", () => {
    it("empties all state and MRU", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { search: "a" });
      useViewStateStore
        .getState()
        .setPageState("m2", "/entities", { search: "b" });

      useViewStateStore.getState().clearAll();

      expect(useViewStateStore.getState().states).toEqual({});
      expect(useViewStateStore.getState().mru).toEqual([]);
    });
  });

  describe("MRU tracking and pruning", () => {
    it("tracks matters in MRU order", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { x: 1 });
      useViewStateStore
        .getState()
        .setPageState("m2", "/documents", { x: 2 });
      useViewStateStore
        .getState()
        .setPageState("m3", "/documents", { x: 3 });

      expect(useViewStateStore.getState().mru).toEqual(["m1", "m2", "m3"]);
    });

    it("moves touched matter to end of MRU", () => {
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { x: 1 });
      useViewStateStore
        .getState()
        .setPageState("m2", "/documents", { x: 2 });
      // Touch m1 again
      useViewStateStore
        .getState()
        .setPageState("m1", "/documents", { x: 10 });

      expect(useViewStateStore.getState().mru).toEqual(["m2", "m1"]);
    });

    it("prunes oldest matters when exceeding limit of 10", () => {
      // Add 12 matters
      for (let i = 1; i <= 12; i++) {
        useViewStateStore
          .getState()
          .setPageState(`m${i}`, "/documents", { x: i });
      }

      const { mru, states } = useViewStateStore.getState();

      // Should keep only the 10 most recent
      expect(mru).toHaveLength(10);
      expect(mru[0]).toBe("m3"); // m1 and m2 pruned
      expect(mru[9]).toBe("m12");

      // Pruned matters should not be in states
      expect(states["m1"]).toBeUndefined();
      expect(states["m2"]).toBeUndefined();
      // Recent matters should still be present
      expect(states["m3"]).toBeDefined();
      expect(states["m12"]).toBeDefined();
    });
  });
});
