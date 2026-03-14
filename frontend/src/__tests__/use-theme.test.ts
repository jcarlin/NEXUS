import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTheme } from "@/hooks/use-theme";

describe("useTheme", () => {
  let matchMediaListeners: Array<(e: { matches: boolean }) => void>;
  let matchMediaMatches: boolean;

  beforeEach(() => {
    matchMediaListeners = [];
    matchMediaMatches = true; // default: system prefers dark
    localStorage.clear();
    document.documentElement.classList.remove("light");
    document.documentElement.classList.remove("dark");

    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query === "(prefers-color-scheme: dark)" && matchMediaMatches,
        media: query,
        addEventListener: (_event: string, handler: (e: { matches: boolean }) => void) => {
          matchMediaListeners.push(handler);
        },
        removeEventListener: (_event: string, handler: (e: { matches: boolean }) => void) => {
          matchMediaListeners = matchMediaListeners.filter((h) => h !== handler);
        },
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to system theme when nothing is stored", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
  });

  it("loads stored theme from localStorage", () => {
    localStorage.setItem("nexus-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    expect(result.current.resolved).toBe("light");
  });

  it("persists theme to localStorage when set", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(localStorage.getItem("nexus-theme")).toBe("light");
    expect(result.current.theme).toBe("light");
  });

  it("toggle switches from dark to light", () => {
    localStorage.setItem("nexus-theme", "dark");
    const { result } = renderHook(() => useTheme());

    expect(result.current.resolved).toBe("dark");

    act(() => {
      result.current.toggle();
    });

    expect(result.current.resolved).toBe("light");
    expect(result.current.theme).toBe("light");
  });

  it("toggle switches from light to dark", () => {
    localStorage.setItem("nexus-theme", "light");
    const { result } = renderHook(() => useTheme());

    expect(result.current.resolved).toBe("light");

    act(() => {
      result.current.toggle();
    });

    expect(result.current.resolved).toBe("dark");
    expect(result.current.theme).toBe("dark");
  });

  it("resolves system theme to dark when system prefers dark", () => {
    matchMediaMatches = true;
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
    expect(result.current.resolved).toBe("dark");
  });

  it("resolves system theme to light when system prefers light", () => {
    matchMediaMatches = false;
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
    expect(result.current.resolved).toBe("light");
  });

  it("applies light class and removes dark class for light mode", () => {
    document.documentElement.classList.add("dark");
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("applies dark class and removes light class for dark mode", () => {
    document.documentElement.classList.add("light");
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(document.documentElement.classList.contains("light")).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
