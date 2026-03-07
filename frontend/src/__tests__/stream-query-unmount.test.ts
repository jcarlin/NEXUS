import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Track abort calls
const abortSpy = vi.fn();

class MockAbortController {
  signal = { aborted: false };
  abort = () => {
    this.signal.aborted = true;
    abortSpy();
  };
}

vi.stubGlobal("AbortController", MockAbortController);

// Mock fetchEventSource to capture invocations without actually streaming
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockFetchEventSource = vi.fn((_url: any, _opts?: any) => Promise.resolve());
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: (url: unknown, opts: unknown) => mockFetchEventSource(url, opts),
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({
      accessToken: "test-token",
      refreshToken: "test-refresh",
      user: {
        id: "1",
        email: "test@test.com",
        full_name: "Test",
        role: "admin",
        is_active: true,
        created_at: "2024-01-01",
      },
      isAuthenticated: true,
    }),
  },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: {
    getState: () => ({
      matterId: "matter-123",
      datasetId: null,
    }),
  },
}));

import { useStreamQuery } from "@/hooks/use-stream-query";

describe("useStreamQuery unmount cleanup", () => {
  beforeEach(() => {
    abortSpy.mockClear();
    mockFetchEventSource.mockClear();
    mockFetchEventSource.mockImplementation(() => Promise.resolve());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls AbortController.abort() on unmount", () => {
    const { result, unmount } = renderHook(() => useStreamQuery());

    // Trigger a stream
    act(() => {
      result.current.send("test query");
    });

    // fetchEventSource should have been called
    expect(mockFetchEventSource).toHaveBeenCalledTimes(1);

    // Unmount the hook
    unmount();

    // abort should have been called (useEffect cleanup)
    expect(abortSpy).toHaveBeenCalled();
  });

  it("aborts previous stream when sending a new query", () => {
    const { result } = renderHook(() => useStreamQuery());

    // Send first query
    act(() => {
      result.current.send("query 1");
    });

    const abortCountAfterFirst = abortSpy.mock.calls.length;

    // Send second query - should abort the first
    act(() => {
      result.current.send("query 2");
    });

    expect(abortSpy.mock.calls.length).toBeGreaterThan(abortCountAfterFirst);
    expect(mockFetchEventSource).toHaveBeenCalledTimes(2);
  });

  it("sets isStreaming to true while streaming", () => {
    const { result } = renderHook(() => useStreamQuery());

    expect(result.current.isStreaming).toBe(false);

    act(() => {
      result.current.send("test query");
    });

    expect(result.current.isStreaming).toBe(true);
  });

  it("cancel() aborts the stream and resets isStreaming", () => {
    const { result } = renderHook(() => useStreamQuery());

    act(() => {
      result.current.send("test query");
    });

    expect(result.current.isStreaming).toBe(true);

    act(() => {
      result.current.cancel();
    });

    expect(abortSpy).toHaveBeenCalled();
    expect(result.current.isStreaming).toBe(false);
  });

  it("does not abort on unmount if no stream was started", () => {
    const { unmount } = renderHook(() => useStreamQuery());

    unmount();

    // abort was never called because no AbortController was created by send()
    // The useEffect cleanup calls abortRef.current?.abort() but ref is null
    expect(abortSpy).not.toHaveBeenCalled();
  });

  it("passes correct headers and body to fetchEventSource", () => {
    const { result } = renderHook(() => useStreamQuery());

    act(() => {
      result.current.send("my question", "thread-abc");
    });

    expect(mockFetchEventSource).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/query/stream"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
          "X-Matter-ID": "matter-123",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          query: "my question",
          thread_id: "thread-abc",
        }),
      }),
    );
  });
});
