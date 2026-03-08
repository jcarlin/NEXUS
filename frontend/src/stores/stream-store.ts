import { create } from "zustand";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";
import { queryClient } from "@/main";
import type { SourceDocument, EntityMention, CitedClaim } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

/** TTL (ms) before completed streams are evicted from the map. */
const COMPLETED_STREAM_TTL = 60_000;

export interface StreamState {
  streamingText: string;
  sources: SourceDocument[];
  stage: string | null;
  isStreaming: boolean;
  citedClaims: CitedClaim[];
  entities: EntityMention[];
  followUps: string[];
  threadId: string | null;
  error: string | null;
  pendingUserMessage: string | null;
  lastQuery: string | null;
}

export const initialStreamState: StreamState = {
  streamingText: "",
  sources: [],
  stage: null,
  isStreaming: false,
  citedClaims: [],
  entities: [],
  followUps: [],
  threadId: null,
  error: null,
  pendingUserMessage: null,
  lastQuery: null,
};

interface ActiveStream {
  state: StreamState;
  abortController: AbortController;
  cleanupTimer?: ReturnType<typeof setTimeout>;
}

interface StreamStore {
  streams: Map<string, ActiveStream>;

  /** Start a stream. Returns the stream key (threadId or temp id). */
  startStream: (query: string, threadId?: string) => string;
  /** Explicitly cancel a stream. */
  cancelStream: (streamKey: string) => void;
  /** Get the active stream for a key. */
  getStream: (streamKey: string) => ActiveStream | undefined;
  /** Find the active new-chat stream key (temp keys start with `_new_`). */
  getNewChatKey: () => string | undefined;
  /** Internal: update state for a stream key. */
  _updateStreamState: (streamKey: string, patch: Partial<StreamState>) => void;
  /** Internal: re-key a stream (temp → real threadId). */
  _rekey: (oldKey: string, newKey: string) => void;
  /** Internal: schedule cleanup of a completed stream. */
  _scheduleCleanup: (streamKey: string) => void;
}

let tempCounter = 0;

export const useStreamStore = create<StreamStore>()((set, get) => ({
  streams: new Map(),

  startStream: (query: string, threadId?: string) => {
    const streamKey = threadId ?? `_new_${++tempCounter}`;

    // Abort any existing stream on this key
    const existing = get().streams.get(streamKey);
    if (existing) {
      existing.abortController.abort();
      if (existing.cleanupTimer) clearTimeout(existing.cleanupTimer);
    }

    const ctrl = new AbortController();
    const entry: ActiveStream = {
      state: {
        ...initialStreamState,
        isStreaming: true,
        stage: "connecting",
        pendingUserMessage: query,
        lastQuery: query,
      },
      abortController: ctrl,
    };

    set((prev) => {
      const next = new Map(prev.streams);
      next.set(streamKey, entry);
      return { streams: next };
    });

    // Read auth/app state outside React
    const accessToken = useAuthStore.getState().accessToken;
    const matterId = useAppStore.getState().matterId;
    const datasetId = useAppStore.getState().datasetId;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    if (matterId) headers["X-Matter-ID"] = matterId;

    fetchEventSource(`${API_BASE}/api/v1/query/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        query,
        ...(threadId ? { thread_id: threadId } : {}),
        dataset_id: datasetId || undefined,
      }),
      signal: ctrl.signal,

      onopen: async (response) => {
        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status}`);
        }
      },

      onmessage: (event) => {
        if (!event.data) return;

        try {
          const parsed = JSON.parse(event.data);

          // Resolve the current key — it may have been re-keyed
          const currentKey = get().streams.has(streamKey)
            ? streamKey
            : undefined;
          if (!currentKey) return;

          switch (event.event) {
            case "status":
              get()._updateStreamState(currentKey, { stage: parsed.stage });
              break;
            case "sources":
              get()._updateStreamState(currentKey, {
                sources: parsed.documents,
              });
              break;
            case "token":
              get()._updateStreamState(currentKey, {
                streamingText:
                  (get().streams.get(currentKey)?.state.streamingText ?? "") +
                  parsed.text,
                stage: "generating",
              });
              break;
            case "done": {
              const realThreadId = parsed.thread_id;

              get()._updateStreamState(currentKey, {
                isStreaming: false,
                stage: null,
                threadId: realThreadId,
                followUps: parsed.follow_ups ?? [],
                entities: parsed.entities ?? [],
                citedClaims: parsed.cited_claims ?? [],
                pendingUserMessage: null,
                streamingText: "",
                sources: [],
              });

              // Re-key temp → real threadId
              if (
                currentKey.startsWith("_new_") &&
                realThreadId &&
                currentKey !== realThreadId
              ) {
                get()._rekey(currentKey, realThreadId);
              }

              // Invalidate TanStack Query caches
              void queryClient.invalidateQueries({
                queryKey: ["chat-thread", realThreadId],
              });
              void queryClient.invalidateQueries({
                queryKey: ["chat-threads"],
              });

              // Schedule eviction
              const finalKey = get().streams.has(realThreadId)
                ? realThreadId
                : currentKey;
              get()._scheduleCleanup(finalKey);
              break;
            }
          }
        } catch {
          // Skip malformed events
        }
      },

      onerror: (err) => {
        if (ctrl.signal.aborted) return;
        const currentKey = get().streams.has(streamKey)
          ? streamKey
          : undefined;
        if (currentKey) {
          get()._updateStreamState(currentKey, {
            isStreaming: false,
            stage: null,
            error:
              err instanceof Error
                ? err.message
                : "Stream connection failed",
            pendingUserMessage: null,
          });
        }
        // Don't retry
        throw err;
      },

      openWhenHidden: true,
    }).catch(() => {
      // fetchEventSource throws on abort or after onerror re-throw; safe to ignore
    });

    return streamKey;
  },

  cancelStream: (streamKey: string) => {
    const entry = get().streams.get(streamKey);
    if (!entry) return;
    entry.abortController.abort();
    get()._updateStreamState(streamKey, {
      isStreaming: false,
      stage: null,
      pendingUserMessage: null,
    });
  },

  getStream: (streamKey: string) => {
    return get().streams.get(streamKey);
  },

  getNewChatKey: () => {
    for (const [key, entry] of get().streams) {
      if (key.startsWith("_new_") && entry.state.isStreaming) return key;
    }
    // Also return completed but not yet cleaned up new-chat streams
    for (const [key] of get().streams) {
      if (key.startsWith("_new_")) return key;
    }
    return undefined;
  },

  _updateStreamState: (streamKey: string, patch: Partial<StreamState>) => {
    set((prev) => {
      const entry = prev.streams.get(streamKey);
      if (!entry) return prev;
      const next = new Map(prev.streams);
      next.set(streamKey, {
        ...entry,
        state: { ...entry.state, ...patch },
      });
      return { streams: next };
    });
  },

  _rekey: (oldKey: string, newKey: string) => {
    set((prev) => {
      const entry = prev.streams.get(oldKey);
      if (!entry) return prev;
      const next = new Map(prev.streams);
      next.delete(oldKey);
      next.set(newKey, entry);
      return { streams: next };
    });
  },

  _scheduleCleanup: (streamKey: string) => {
    const entry = get().streams.get(streamKey);
    if (!entry) return;
    if (entry.cleanupTimer) clearTimeout(entry.cleanupTimer);

    const timer = setTimeout(() => {
      set((prev) => {
        const next = new Map(prev.streams);
        next.delete(streamKey);
        return { streams: next };
      });
    }, COMPLETED_STREAM_TTL);

    set((prev) => {
      const existing = prev.streams.get(streamKey);
      if (!existing) return prev;
      const next = new Map(prev.streams);
      next.set(streamKey, { ...existing, cleanupTimer: timer });
      return { streams: next };
    });
  },
}));
