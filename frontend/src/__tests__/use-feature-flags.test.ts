import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const mockApiClient = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: (...args: unknown[]) => mockApiClient(...args),
}));

import { useFeatureFlags, useFeatureFlag } from "@/hooks/use-feature-flags";

const ALL_FLAGS = {
  hot_doc_detection: true,
  case_setup_agent: false,
  topic_clustering: true,
  graph_centrality: false,
  sparse_embeddings: true,
  near_duplicate_detection: false,
  reranker: true,
  redaction: false,
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useFeatureFlags", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiClient.mockResolvedValue(ALL_FLAGS);
  });

  it("returns feature flags from API", async () => {
    const { result } = renderHook(() => useFeatureFlags(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(ALL_FLAGS);
  });

  it("calls the correct endpoint", async () => {
    const { result } = renderHook(() => useFeatureFlags(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith({
      url: "/api/v1/config/features",
      method: "GET",
    });
  });
});

describe("useFeatureFlag", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiClient.mockResolvedValue(ALL_FLAGS);
  });

  it("returns true for an enabled flag", async () => {
    const { result } = renderHook(() => useFeatureFlag("hot_doc_detection"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current).toBe(true));
  });

  it("returns false for a disabled flag", async () => {
    const { result } = renderHook(() => useFeatureFlag("case_setup_agent"), {
      wrapper: createWrapper(),
    });

    // Initially false (loading), stays false because flag is disabled
    expect(result.current).toBe(false);
    await waitFor(() => expect(mockApiClient).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  it("returns false while loading", () => {
    mockApiClient.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useFeatureFlag("hot_doc_detection"), {
      wrapper: createWrapper(),
    });

    expect(result.current).toBe(false);
  });
});
