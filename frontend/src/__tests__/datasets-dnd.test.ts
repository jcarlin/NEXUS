import { describe, it, expect } from "vitest";
import {
  buildDragPayload,
  toggleSelection,
  isAllSelected,
} from "@/lib/dataset-dnd";

describe("buildDragPayload", () => {
  it("returns all selected IDs when dragged doc is in selection", () => {
    const selected = new Set(["a", "b", "c"]);
    const result = buildDragPayload("b", selected);
    expect(result).toHaveLength(3);
    expect(result).toContain("a");
    expect(result).toContain("b");
    expect(result).toContain("c");
  });

  it("returns only the dragged doc when it is not in selection", () => {
    const selected = new Set(["a", "b"]);
    const result = buildDragPayload("d", selected);
    expect(result).toEqual(["d"]);
  });

  it("returns the dragged doc when selection is empty", () => {
    const result = buildDragPayload("x", new Set());
    expect(result).toEqual(["x"]);
  });
});

describe("toggleSelection", () => {
  it("adds an ID not in the set", () => {
    const result = toggleSelection(new Set(["a"]), "b");
    expect(result).toEqual(new Set(["a", "b"]));
  });

  it("removes an ID already in the set", () => {
    const result = toggleSelection(new Set(["a", "b"]), "b");
    expect(result).toEqual(new Set(["a"]));
  });

  it("does not mutate the original set", () => {
    const original = new Set(["a"]);
    toggleSelection(original, "b");
    expect(original).toEqual(new Set(["a"]));
  });
});

describe("isAllSelected", () => {
  it("returns true when all page IDs are selected", () => {
    expect(isAllSelected(new Set(["a", "b", "c"]), ["a", "b"])).toBe(true);
  });

  it("returns false when some page IDs are not selected", () => {
    expect(isAllSelected(new Set(["a"]), ["a", "b"])).toBe(false);
  });

  it("returns false for empty page", () => {
    expect(isAllSelected(new Set(["a"]), [])).toBe(false);
  });
});
