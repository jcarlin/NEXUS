import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth-store";

describe("auth store", () => {
  beforeEach(() => {
    useAuthStore.getState().logout(); // reset
  });

  it("login sets tokens, user, and isAuthenticated", () => {
    const user = { id: "1", email: "a@b.com", full_name: "Test", role: "admin" as const, is_active: true, created_at: "2024-01-01" };
    useAuthStore.getState().login("access-tok", "refresh-tok", user);
    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access-tok");
    expect(state.refreshToken).toBe("refresh-tok");
    expect(state.user).toEqual(user);
    expect(state.isAuthenticated).toBe(true);
  });

  it("logout clears all state", () => {
    const user = { id: "1", email: "a@b.com", full_name: "Test", role: "admin" as const, is_active: true, created_at: "2024-01-01" };
    useAuthStore.getState().login("access-tok", "refresh-tok", user);
    useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("setTokens updates tokens without clearing user", () => {
    const user = { id: "1", email: "a@b.com", full_name: "Test", role: "admin" as const, is_active: true, created_at: "2024-01-01" };
    useAuthStore.getState().login("old-access", "old-refresh", user);
    useAuthStore.getState().setTokens("new-access", "new-refresh");
    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("new-access");
    expect(state.refreshToken).toBe("new-refresh");
    expect(state.user).toEqual(user);
  });
});
