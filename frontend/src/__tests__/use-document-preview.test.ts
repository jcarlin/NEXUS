import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDocumentPreview } from "@/hooks/use-document-preview";

vi.mock("@/api/client", () => ({
  apiFetchRaw: vi.fn(),
}));

import { apiFetchRaw } from "@/api/client";

const mockApiFetchRaw = vi.mocked(apiFetchRaw);

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
  const fakeObjectUrl = "blob:http://localhost/fake-url";

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "URL",
      Object.assign({}, globalThis.URL, {
        createObjectURL: vi.fn(() => fakeObjectUrl),
        revokeObjectURL: vi.fn(),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns null previewUrl when docId is null", () => {
    const { result } = renderHook(() => useDocumentPreview(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.previewUrl).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(mockApiFetchRaw).not.toHaveBeenCalled();
  });

  it("fetches preview and creates object URL for a valid docId", async () => {
    mockApiFetchRaw.mockResolvedValueOnce({
      blob: () => Promise.resolve(new Blob(["fake-image"], { type: "image/png" })),
    } as unknown as Response);

    const { result } = renderHook(() => useDocumentPreview("doc-1", 3), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.previewUrl).toBe(fakeObjectUrl);
    expect(mockApiFetchRaw).toHaveBeenCalledWith(
      "/api/v1/documents/doc-1/preview?page=3",
      expect.anything(),
    );
  });

  it("defaults to page 1 when page is null", async () => {
    mockApiFetchRaw.mockResolvedValueOnce({
      blob: () => Promise.resolve(new Blob()),
    } as unknown as Response);

    const { result } = renderHook(() => useDocumentPreview("doc-1", null), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockApiFetchRaw).toHaveBeenCalledWith(
      "/api/v1/documents/doc-1/preview?page=1",
      expect.anything(),
    );
  });

  it("returns error when fetch fails", async () => {
    mockApiFetchRaw.mockRejectedValueOnce(new Error("Not found"));

    const { result } = renderHook(() => useDocumentPreview("doc-bad"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.previewUrl).toBeNull();
    expect(result.current.error?.message).toBe("Not found");
  });
});
