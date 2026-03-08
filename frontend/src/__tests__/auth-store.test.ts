import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { User } from "@/types";

const TEST_USER: User = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  role: "admin",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

const TEST_USER_2: User = {
  id: "user-2",
  email: "other@example.com",
  full_name: "Other User",
  role: "viewer",
  is_active: true,
  created_at: "2024-02-01T00:00:00Z",
};

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
  });

  it("starts with null tokens and isAuthenticated=false", () => {
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("login() sets accessToken, refreshToken, user, isAuthenticated=true", () => {
    useAuthStore.getState().login("access-123", "refresh-456", TEST_USER);

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access-123");
    expect(state.refreshToken).toBe("refresh-456");
    expect(state.user).toEqual(TEST_USER);
    expect(state.isAuthenticated).toBe(true);
  });

  it("setTokens() updates only tokens without changing user or isAuthenticated", () => {
    useAuthStore.getState().login("access-old", "refresh-old", TEST_USER);
    useAuthStore.getState().setTokens("access-new", "refresh-new");

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access-new");
    expect(state.refreshToken).toBe("refresh-new");
    expect(state.user).toEqual(TEST_USER);
    expect(state.isAuthenticated).toBe(true);
  });

  it("setUser() updates only user without changing tokens", () => {
    useAuthStore.getState().login("access-123", "refresh-456", TEST_USER);
    useAuthStore.getState().setUser(TEST_USER_2);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(TEST_USER_2);
    expect(state.accessToken).toBe("access-123");
    expect(state.refreshToken).toBe("refresh-456");
  });

  it("logout() clears everything and sets isAuthenticated=false", () => {
    useAuthStore.getState().login("access-123", "refresh-456", TEST_USER);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("login() after logout() restores authenticated state", () => {
    useAuthStore.getState().login("a1", "r1", TEST_USER);
    useAuthStore.getState().logout();
    useAuthStore.getState().login("a2", "r2", TEST_USER_2);

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("a2");
    expect(state.refreshToken).toBe("r2");
    expect(state.user).toEqual(TEST_USER_2);
    expect(state.isAuthenticated).toBe(true);
  });

  it("setTokens() on unauthenticated store updates tokens only", () => {
    useAuthStore.getState().setTokens("new-access", "new-refresh");

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("new-access");
    expect(state.refreshToken).toBe("new-refresh");
    expect(state.user).toBeNull();
  });

  it("setUser() on unauthenticated store updates user only", () => {
    useAuthStore.getState().setUser(TEST_USER);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(TEST_USER);
    expect(state.accessToken).toBeNull();
  });

  it("multiple login() calls overwrite previous state", () => {
    useAuthStore.getState().login("a1", "r1", TEST_USER);
    useAuthStore.getState().login("a2", "r2", TEST_USER_2);

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("a2");
    expect(state.user?.email).toBe("other@example.com");
  });

  it("logout() is idempotent", () => {
    useAuthStore.getState().logout();
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
  });
});
