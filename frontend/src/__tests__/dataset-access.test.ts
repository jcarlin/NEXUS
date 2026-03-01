import { describe, it, expect } from "vitest";
import {
  canManageDatasetAccess,
  filterAvailableUsers,
} from "@/lib/dataset-access";

describe("canManageDatasetAccess", () => {
  it("returns true for admin", () => {
    expect(canManageDatasetAccess("admin")).toBe(true);
  });

  it("returns true for attorney", () => {
    expect(canManageDatasetAccess("attorney")).toBe(true);
  });

  it("returns false for paralegal", () => {
    expect(canManageDatasetAccess("paralegal")).toBe(false);
  });

  it("returns false for reviewer", () => {
    expect(canManageDatasetAccess("reviewer")).toBe(false);
  });

  it("returns false for null/undefined", () => {
    expect(canManageDatasetAccess(null)).toBe(false);
    expect(canManageDatasetAccess(undefined)).toBe(false);
  });
});

describe("filterAvailableUsers", () => {
  const users = [{ id: "u1" }, { id: "u2" }, { id: "u3" }];

  it("excludes users already granted access", () => {
    const granted = [{ user_id: "u2" }];
    const result = filterAvailableUsers(users, granted);
    expect(result).toEqual([{ id: "u1" }, { id: "u3" }]);
  });

  it("returns all users when no access grants exist", () => {
    const result = filterAvailableUsers(users, []);
    expect(result).toEqual(users);
  });

  it("returns empty when all users are granted", () => {
    const granted = [
      { user_id: "u1" },
      { user_id: "u2" },
      { user_id: "u3" },
    ];
    const result = filterAvailableUsers(users, granted);
    expect(result).toEqual([]);
  });
});
