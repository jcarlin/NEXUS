import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDocumentPreview } from "@/hooks/use-document-preview";

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

import { apiClient } from "@/api/client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("useDocumentPreview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns null previewUrl when docId is null", () => {
    const { result } = renderHook(() => useDocumentPreview(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.previewUrl).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("fetches preview URL for a valid docId", async () => {
    mockApiClient.mockResolvedValueOnce({ preview_url: "https://example.com/preview.png" });

    const { result } = renderHook(() => useDocumentPreview("doc-1", 3), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.previewUrl).toBe("https://example.com/preview.png");
    expect(mockApiClient).toHaveBeenCalledWith({
      url: "/api/v1/documents/doc-1/preview",
      method: "GET",
      params: { page: 3 },
    });
  });

  it("defaults to page 1 when page is null", async () => {
    mockApiClient.mockResolvedValueOnce({ preview_url: "https://example.com/p1.png" });

    const { result } = renderHook(() => useDocumentPreview("doc-1", null), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockApiClient).toHaveBeenCalledWith(
      expect.objectContaining({ params: { page: 1 } }),
    );
  });

  it("returns error when fetch fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Not found"));

    const { result } = renderHook(() => useDocumentPreview("doc-bad"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.previewUrl).toBeNull();
    expect(result.current.error?.message).toBe("Not found");
  });
});
