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

vi.mock("@/main", () => ({
  queryClient: {
    invalidateQueries: vi.fn(() => Promise.resolve()),
  },
}));

import { useStreamQuery } from "@/hooks/use-stream-query";
import { useStreamStore } from "@/stores/stream-store";

describe("useStreamQuery with global stream store", () => {
  beforeEach(() => {
    abortSpy.mockClear();
    mockFetchEventSource.mockClear();
    mockFetchEventSource.mockImplementation(() => Promise.resolve());
    // Reset the store between tests
    useStreamStore.setState({ streams: new Map() });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does NOT abort on unmount — stream survives component unmount", () => {
    const { result, unmount } = renderHook(() => useStreamQuery());

    // Trigger a stream
    act(() => {
      result.current.send("test query");
    });

    expect(mockFetchEventSource).toHaveBeenCalledTimes(1);

    // Unmount the hook — should NOT abort
    unmount();

    // abort should NOT have been called (stream persists globally)
    expect(abortSpy).not.toHaveBeenCalled();
  });

  it("active stream survives component unmount and is accessible from new hook", () => {
    const { result, unmount } = renderHook(() => useStreamQuery());

    act(() => {
      result.current.send("test query");
    });

    expect(result.current.isStreaming).toBe(true);

    // Unmount
    unmount();

    // The stream should still exist in the store
    const store = useStreamStore.getState();
    const newChatKey = store.getNewChatKey();
    expect(newChatKey).toBeDefined();
    expect(store.streams.get(newChatKey!)?.state.isStreaming).toBe(true);
  });

  it("navigating back to thread picks up active stream", () => {
    const threadId = "thread-abc";

    // First render — start a stream on a thread
    const { result: result1, unmount: unmount1 } = renderHook(() =>
      useStreamQuery(threadId),
    );

    act(() => {
      result1.current.send("test query");
    });

    expect(result1.current.isStreaming).toBe(true);

    // Unmount (navigate away)
    unmount1();

    // Re-render with same threadId (navigate back)
    const { result: result2 } = renderHook(() => useStreamQuery(threadId));

    // Should see the same stream state
    expect(result2.current.isStreaming).toBe(true);
    expect(result2.current.lastQuery).toBe("test query");
  });

  it("explicit cancel() still aborts the stream", () => {
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

  it("completed streams are cleaned up after TTL", () => {
    vi.useFakeTimers();

    const threadId = "thread-cleanup";

    // Simulate a completed stream by directly setting store state
    const ctrl = new MockAbortController();
    useStreamStore.setState({
      streams: new Map([
        [
          threadId,
          {
            state: {
              streamingText: "done text",
              sources: [],
              stage: null,
              isStreaming: false,
              citedClaims: [],
              entities: [],
              followUps: [],
              threadId,
              error: null,
              pendingUserMessage: null,
              lastQuery: "test",
              clarificationQuestion: null,
            },
            abortController: ctrl as unknown as AbortController,
          },
        ],
      ]),
    });

    // Schedule cleanup
    act(() => {
      useStreamStore.getState()._scheduleCleanup(threadId);
    });

    // Stream should still be there
    expect(useStreamStore.getState().streams.has(threadId)).toBe(true);

    // Advance past TTL (60s)
    act(() => {
      vi.advanceTimersByTime(61_000);
    });

    // Stream should be evicted
    expect(useStreamStore.getState().streams.has(threadId)).toBe(false);

    vi.useRealTimers();
  });

  it("aborts previous stream when sending a new query on same thread", () => {
    const threadId = "thread-reuse";
    const { result } = renderHook(() => useStreamQuery(threadId));

    act(() => {
      result.current.send("query 1");
    });

    const abortCountAfterFirst = abortSpy.mock.calls.length;

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

  it("does not abort on unmount if no stream was started", () => {
    const { unmount } = renderHook(() => useStreamQuery());
    unmount();
    expect(abortSpy).not.toHaveBeenCalled();
  });

  it("passes correct headers and body to fetchEventSource", () => {
    const { result } = renderHook(() => useStreamQuery("thread-abc"));

    act(() => {
      result.current.send("my question");
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
