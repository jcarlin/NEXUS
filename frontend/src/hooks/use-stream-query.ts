import { useCallback, useMemo, useRef } from "react";
import { useStreamStore, initialStreamState } from "@/stores/stream-store";
import type { StreamState } from "@/stores/stream-store";

/**
 * Thin hook over the global stream store.
 *
 * When `threadId` is provided, subscribes to that thread's active stream.
 * When omitted (new-chat page), subscribes to the temp new-chat stream.
 *
 * The hook's API surface is identical to the previous component-scoped version
 * so consumers (ChatPage, ChatThreadPage) need minimal changes.
 */
export function useStreamQuery(threadId?: string) {
  // Track the temp key created by this hook instance for new-chat flows
  const tempKeyRef = useRef<string | null>(null);

  const streamEntry = useStreamStore((s) => {
    if (threadId) {
      return s.streams.get(threadId);
    }
    // New-chat: check our temp key first, then any active new-chat stream
    if (tempKeyRef.current) {
      const entry = s.streams.get(tempKeyRef.current);
      if (entry) return entry;
    }
    const newKey = s.getNewChatKey();
    return newKey ? s.streams.get(newKey) : undefined;
  });

  const startStream = useStreamStore((s) => s.startStream);
  const cancelStreamAction = useStreamStore((s) => s.cancelStream);
  const resumeStreamAction = useStreamStore((s) => s.resumeStream);

  const state: StreamState = streamEntry?.state ?? initialStreamState;

  // Resolve the active key for cancel operations
  const activeKey = useMemo(() => {
    if (threadId) return threadId;
    if (tempKeyRef.current) return tempKeyRef.current;
    return useStreamStore.getState().getNewChatKey() ?? null;
  }, [threadId, streamEntry]);

  const send = useCallback(
    (query: string) => {
      const key = startStream(query, threadId);
      if (!threadId) {
        tempKeyRef.current = key;
      }
    },
    [threadId, startStream],
  );

  const cancel = useCallback(() => {
    if (activeKey) cancelStreamAction(activeKey);
  }, [activeKey, cancelStreamAction]);

  const resume = useCallback(
    (answer: string) => {
      const key = activeKey ?? state.threadId;
      if (key) resumeStreamAction(key, answer);
    },
    [activeKey, state.threadId, resumeStreamAction],
  );

  // NO useEffect cleanup that aborts on unmount — stream survives navigation

  return { ...state, send, cancel, resume };
}

export type { StreamState };
