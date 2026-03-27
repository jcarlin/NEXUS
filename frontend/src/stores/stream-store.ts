import { create } from "zustand";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";
import { queryClient } from "@/main";
import type { SourceDocument, EntityMention, CitedClaim, ToolCallEntry, TraceStep, TraceSummary } from "@/types";
import type { OverrideValue } from "@/stores/override-store";
import { useDevModeStore } from "@/stores/dev-mode-store";

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
  toolCalls: ToolCallEntry[];
  traceSteps: TraceStep[];
  traceSummary: TraceSummary | null;
  threadId: string | null;
  error: string | null;
  clarificationQuestion: string | null;
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
  toolCalls: [],
  traceSteps: [],
  traceSummary: null,
  threadId: null,
  error: null,
  clarificationQuestion: null,
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
  startStream: (query: string, threadId?: string, overrides?: Record<string, OverrideValue>) => string;
  /** Explicitly cancel a stream. */
  cancelStream: (streamKey: string) => void;
  /** Resume a paused stream after clarification. */
  resumeStream: (threadId: string, answer: string) => void;
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

  startStream: (query: string, threadId?: string, overrides?: Record<string, OverrideValue>) => {
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

    const devMode = useDevModeStore.getState().enabled;

    fetchEventSource(`${API_BASE}/api/v1/query/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        query,
        ...(threadId ? { thread_id: threadId } : {}),
        dataset_id: datasetId || undefined,
        retrieval_overrides:
          overrides && Object.keys(overrides).length > 0
            ? overrides
            : undefined,
        ...(devMode ? { debug: true } : {}),
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
            case "clear":
              // Agent made a tool call after emitting "thinking" tokens —
              // discard the partial text so only the final answer is shown.
              get()._updateStreamState(currentKey, {
                streamingText: "",
                stage: "investigating",
              });
              break;
            case "tool_call":
              get()._updateStreamState(currentKey, {
                toolCalls: [
                  ...(get().streams.get(currentKey)?.state.toolCalls ?? []),
                  { tool: parsed.tool, label: parsed.label },
                ],
              });
              break;
            case "trace_step":
              get()._updateStreamState(currentKey, {
                traceSteps: [
                  ...(get().streams.get(currentKey)?.state.traceSteps ?? []),
                  parsed as TraceStep,
                ],
              });
              break;
            case "trace_summary":
              get()._updateStreamState(currentKey, {
                traceSummary: parsed as TraceSummary,
              });
              break;
            case "interrupt": {
              get()._updateStreamState(currentKey, {
                isStreaming: false,
                stage: "awaiting_clarification",
                clarificationQuestion: parsed.question,
              });
              // Re-key temp → real threadId (same as done)
              const intThreadId = parsed.thread_id;
              if (
                currentKey.startsWith("_new_") &&
                intThreadId &&
                currentKey !== intThreadId
              ) {
                get()._rekey(currentKey, intThreadId);
              }
              // Do NOT schedule cleanup — stream will resume after clarification
              break;
            }
            case "error":
              get()._updateStreamState(currentKey, {
                isStreaming: false,
                stage: null,
                error: parsed.message || "Something went wrong",
                pendingUserMessage: null,
              });
              get()._scheduleCleanup(currentKey);
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
                // Keep streamingText and sources intact — thread page reads
                // them after navigation. The cleanup timer will evict after
                // COMPLETED_STREAM_TTL.
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

              // Schedule eviction for both the real key and the _new_ alias
              if (realThreadId) {
                get()._scheduleCleanup(realThreadId);
              }
              if (currentKey !== realThreadId) {
                get()._scheduleCleanup(currentKey);
              }
              break;
            }
          }
        } catch (err) {
          console.error("Stream: malformed SSE event", event.event, err);
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
    }).catch((err) => {
      // fetchEventSource throws on abort — that's expected and safe to ignore.
      // Log anything else so connection failures are visible in dev tools.
      if (!ctrl.signal.aborted) {
        console.error("Stream connection error:", err);
      }
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

  resumeStream: (threadId: string, answer: string) => {
    // Reset clarification state
    get()._updateStreamState(threadId, {
      isStreaming: true,
      stage: "resuming",
      clarificationQuestion: null,
      error: null,
    });

    const ctrl = new AbortController();
    // Update the abort controller
    const existing = get().streams.get(threadId);
    if (existing) {
      existing.abortController.abort();
      set((prev) => {
        const next = new Map(prev.streams);
        const entry = next.get(threadId);
        if (entry) {
          next.set(threadId, { ...entry, abortController: ctrl });
        }
        return { streams: next };
      });
    }

    const accessToken = useAuthStore.getState().accessToken;
    const matterId = useAppStore.getState().matterId;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    if (matterId) headers["X-Matter-ID"] = matterId;

    fetchEventSource(`${API_BASE}/api/v1/query/resume`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        thread_id: threadId,
        answer,
      }),
      signal: ctrl.signal,

      onopen: async (response) => {
        if (!response.ok) {
          throw new Error(`Resume stream failed: ${response.status}`);
        }
      },

      onmessage: (event) => {
        if (!event.data) return;

        try {
          const parsed = JSON.parse(event.data);
          const currentKey = get().streams.has(threadId)
            ? threadId
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
            case "clear":
              get()._updateStreamState(currentKey, {
                streamingText: "",
                stage: "investigating",
              });
              break;
            case "tool_call":
              get()._updateStreamState(currentKey, {
                toolCalls: [
                  ...(get().streams.get(currentKey)?.state.toolCalls ?? []),
                  { tool: parsed.tool, label: parsed.label },
                ],
              });
              break;
            case "trace_step":
              get()._updateStreamState(currentKey, {
                traceSteps: [
                  ...(get().streams.get(currentKey)?.state.traceSteps ?? []),
                  parsed as TraceStep,
                ],
              });
              break;
            case "trace_summary":
              get()._updateStreamState(currentKey, {
                traceSummary: parsed as TraceSummary,
              });
              break;
            case "interrupt": {
              get()._updateStreamState(currentKey, {
                isStreaming: false,
                stage: "awaiting_clarification",
                clarificationQuestion: parsed.question,
              });
              break;
            }
            case "error":
              get()._updateStreamState(currentKey, {
                isStreaming: false,
                stage: null,
                error: parsed.message || "Something went wrong",
                clarificationQuestion: null,
              });
              get()._scheduleCleanup(currentKey);
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
                clarificationQuestion: null,
              });

              void queryClient.invalidateQueries({
                queryKey: ["chat-thread", realThreadId],
              });
              void queryClient.invalidateQueries({
                queryKey: ["chat-threads"],
              });

              if (realThreadId) {
                get()._scheduleCleanup(realThreadId);
              }
              if (currentKey !== realThreadId) {
                get()._scheduleCleanup(currentKey);
              }
              break;
            }
          }
        } catch (err) {
          console.error("Resume stream: malformed SSE event", event.event, err);
        }
      },

      onerror: (err) => {
        if (ctrl.signal.aborted) return;
        get()._updateStreamState(threadId, {
          isStreaming: false,
          stage: null,
          error:
            err instanceof Error
              ? err.message
              : "Resume stream connection failed",
          clarificationQuestion: null,
        });
        throw err;
      },

      openWhenHidden: true,
    }).catch((err) => {
      if (!ctrl.signal.aborted) {
        console.error("Resume stream connection error:", err);
      }
    });
  },

  getStream: (streamKey: string) => {
    return get().streams.get(streamKey);
  },

  getNewChatKey: () => {
    for (const [key, entry] of get().streams) {
      if (key.startsWith("_new_") && entry.state.isStreaming) return key;
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
      // Keep old key as alias so the new-chat page can still find the
      // stream for auto-navigation.  Both keys are cleaned up by the TTL.
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
