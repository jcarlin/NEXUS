import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useStreamStore, initialStreamState } from "@/stores/stream-store";
import type { StreamState } from "@/stores/stream-store";

// Mock external dependencies that the store imports
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({
      accessToken: "test-token",
    }),
  },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: {
    getState: () => ({
      matterId: "matter-1",
      datasetId: null,
    }),
  },
}));

vi.mock("@/main", () => ({
  queryClient: {
    invalidateQueries: vi.fn(() => Promise.resolve()),
  },
}));

function makeStreamState(overrides: Partial<StreamState> = {}): StreamState {
  return { ...initialStreamState, ...overrides };
}

describe("useStreamStore", () => {
  beforeEach(() => {
    useStreamStore.setState({ streams: new Map() });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts with empty streams map", () => {
    expect(useStreamStore.getState().streams.size).toBe(0);
  });

  it("initialStreamState has correct defaults", () => {
    expect(initialStreamState.streamingText).toBe("");
    expect(initialStreamState.sources).toEqual([]);
    expect(initialStreamState.stage).toBeNull();
    expect(initialStreamState.isStreaming).toBe(false);
    expect(initialStreamState.citedClaims).toEqual([]);
    expect(initialStreamState.entities).toEqual([]);
    expect(initialStreamState.followUps).toEqual([]);
    expect(initialStreamState.threadId).toBeNull();
    expect(initialStreamState.error).toBeNull();
    expect(initialStreamState.pendingUserMessage).toBeNull();
    expect(initialStreamState.lastQuery).toBeNull();
  });

  it("startStream creates a new stream entry", () => {
    const key = useStreamStore.getState().startStream("test query");
    expect(key).toBeDefined();
    expect(useStreamStore.getState().streams.has(key)).toBe(true);
  });

  it("startStream sets isStreaming=true and pendingUserMessage", () => {
    const key = useStreamStore.getState().startStream("test query");
    const entry = useStreamStore.getState().streams.get(key);
    expect(entry?.state.isStreaming).toBe(true);
    expect(entry?.state.pendingUserMessage).toBe("test query");
    expect(entry?.state.lastQuery).toBe("test query");
  });

  it("startStream uses threadId as key when provided", () => {
    const key = useStreamStore.getState().startStream("query", "thread-123");
    expect(key).toBe("thread-123");
  });

  it("startStream uses temp key when no threadId", () => {
    const key = useStreamStore.getState().startStream("query");
    expect(key.startsWith("_new_")).toBe(true);
  });

  it("cancelStream aborts and sets isStreaming=false", () => {
    const key = useStreamStore.getState().startStream("query");
    useStreamStore.getState().cancelStream(key);

    const entry = useStreamStore.getState().streams.get(key);
    expect(entry?.state.isStreaming).toBe(false);
    expect(entry?.state.pendingUserMessage).toBeNull();
  });

  it("cancelStream is a no-op for non-existent key", () => {
    // Should not throw
    useStreamStore.getState().cancelStream("does-not-exist");
    expect(useStreamStore.getState().streams.size).toBe(0);
  });

  it("getStream returns stream by key", () => {
    const key = useStreamStore.getState().startStream("query");
    const stream = useStreamStore.getState().getStream(key);
    expect(stream).toBeDefined();
    expect(stream?.state.lastQuery).toBe("query");
  });

  it("getStream returns undefined for non-existent key", () => {
    expect(useStreamStore.getState().getStream("missing")).toBeUndefined();
  });

  it("getNewChatKey finds active new-chat stream", () => {
    const key = useStreamStore.getState().startStream("query");
    expect(key.startsWith("_new_")).toBe(true);
    const found = useStreamStore.getState().getNewChatKey();
    expect(found).toBe(key);
  });

  it("getNewChatKey returns undefined when no new-chat streams", () => {
    useStreamStore.getState().startStream("query", "thread-123");
    expect(useStreamStore.getState().getNewChatKey()).toBeUndefined();
  });

  it("_updateStreamState patches state for a key", () => {
    const key = useStreamStore.getState().startStream("query");
    useStreamStore.getState()._updateStreamState(key, {
      streamingText: "Hello world",
      stage: "generating",
    });

    const entry = useStreamStore.getState().streams.get(key);
    expect(entry?.state.streamingText).toBe("Hello world");
    expect(entry?.state.stage).toBe("generating");
    // Other fields should be unchanged
    expect(entry?.state.isStreaming).toBe(true);
  });

  it("_updateStreamState is a no-op for non-existent key", () => {
    const sizeBefore = useStreamStore.getState().streams.size;
    useStreamStore.getState()._updateStreamState("nope", { stage: "x" });
    expect(useStreamStore.getState().streams.size).toBe(sizeBefore);
  });

  it("_rekey moves a stream from old key to new key", () => {
    const oldKey = useStreamStore.getState().startStream("query");
    useStreamStore.getState()._rekey(oldKey, "thread-real");

    expect(useStreamStore.getState().streams.has(oldKey)).toBe(false);
    expect(useStreamStore.getState().streams.has("thread-real")).toBe(true);
    expect(
      useStreamStore.getState().streams.get("thread-real")?.state.lastQuery,
    ).toBe("query");
  });

  it("_rekey is a no-op when old key does not exist", () => {
    useStreamStore.getState()._rekey("nonexistent", "new");
    expect(useStreamStore.getState().streams.size).toBe(0);
  });

  it("_scheduleCleanup removes stream after TTL", () => {
    vi.useFakeTimers();

    const key = useStreamStore.getState().startStream("query", "thread-cleanup");
    useStreamStore.getState()._updateStreamState(key, { isStreaming: false });
    useStreamStore.getState()._scheduleCleanup(key);

    // Still there immediately
    expect(useStreamStore.getState().streams.has(key)).toBe(true);

    // Advance past the 60s TTL
    vi.advanceTimersByTime(61_000);

    expect(useStreamStore.getState().streams.has(key)).toBe(false);

    vi.useRealTimers();
  });

  it("startStream aborts existing stream on same key", () => {
    const key = "thread-reuse";
    useStreamStore.getState().startStream("query 1", key);
    const firstEntry = useStreamStore.getState().streams.get(key)!;
    const abortSpy = vi.spyOn(firstEntry.abortController, "abort");

    useStreamStore.getState().startStream("query 2", key);
    expect(abortSpy).toHaveBeenCalled();
    expect(
      useStreamStore.getState().streams.get(key)?.state.lastQuery,
    ).toBe("query 2");
  });

  it("multiple concurrent streams can coexist", () => {
    useStreamStore.getState().startStream("query", "thread-a");
    useStreamStore.getState().startStream("query", "thread-b");
    expect(useStreamStore.getState().streams.size).toBe(2);
  });
});
