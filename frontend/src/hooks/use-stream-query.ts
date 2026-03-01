import { useState, useCallback, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";
import type {
  SourceDocument,
  EntityMention,
  CitedClaim,
} from "@/types";

interface StreamState {
  streamingText: string;
  sources: SourceDocument[];
  stage: string | null;
  isStreaming: boolean;
  citedClaims: CitedClaim[];
  entities: EntityMention[];
  followUps: string[];
  threadId: string | null;
  error: string | null;
}

const initialState: StreamState = {
  streamingText: "",
  sources: [],
  stage: null,
  isStreaming: false,
  citedClaims: [],
  entities: [],
  followUps: [],
  threadId: null,
  error: null,
};

export function useStreamQuery() {
  const [state, setState] = useState<StreamState>(initialState);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback((query: string, threadId?: string) => {
    // Abort any existing stream
    abortRef.current?.abort();

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const accessToken = useAuthStore.getState().accessToken;
    const matterId = useAppStore.getState().matterId;

    setState({
      ...initialState,
      isStreaming: true,
      stage: "connecting",
    });

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    if (matterId) headers["X-Matter-ID"] = matterId;

    fetchEventSource("/api/v1/query/stream", {
      method: "POST",
      headers,
      body: JSON.stringify({
        query,
        ...(threadId ? { thread_id: threadId } : {}),
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

          switch (parsed.type) {
            case "status":
              setState((prev) => ({ ...prev, stage: parsed.stage }));
              break;
            case "sources":
              setState((prev) => ({
                ...prev,
                sources: parsed.documents,
              }));
              break;
            case "token":
              setState((prev) => ({
                ...prev,
                streamingText: prev.streamingText + parsed.text,
                stage: "generating",
              }));
              break;
            case "done":
              setState((prev) => ({
                ...prev,
                isStreaming: false,
                stage: null,
                threadId: parsed.thread_id,
                followUps: parsed.follow_ups ?? [],
                entities: parsed.entities ?? [],
                citedClaims: parsed.cited_claims ?? [],
              }));
              break;
          }
        } catch {
          // Skip malformed events
        }
      },

      onerror: (err) => {
        if (ctrl.signal.aborted) return;
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          stage: null,
          error: err instanceof Error ? err.message : "Stream connection failed",
        }));
        // Don't retry — let the user re-send
        throw err;
      },

      openWhenHidden: true,
    }).catch(() => {
      // fetchEventSource throws on abort or after onerror re-throw; safe to ignore
    });
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isStreaming: false, stage: null }));
  }, []);

  return { ...state, send, cancel };
}
