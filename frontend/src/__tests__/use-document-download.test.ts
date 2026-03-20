import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDocumentDownload } from "@/hooks/use-document-download";

vi.mock("@/api/client", () => ({
  apiFetchRaw: vi.fn(),
}));

import { apiFetchRaw } from "@/api/client";

const mockApiFetchRaw = vi.mocked(apiFetchRaw);

const fakeObjectUrl = "blob:http://localhost/fake-url";
const mockCreateObjectURL = vi.fn(() => fakeObjectUrl);
const mockRevokeObjectURL = vi.fn();

// Patch URL methods directly so they persist through React cleanup effects
globalThis.URL.createObjectURL = mockCreateObjectURL;
globalThis.URL.revokeObjectURL = mockRevokeObjectURL;

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

describe("useDocumentDownload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns null downloadUrl when docId is null", () => {
    const { result } = renderHook(() => useDocumentDownload(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.downloadUrl).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(mockApiFetchRaw).not.toHaveBeenCalled();
  });

  it("fetches download and creates object URL for a valid docId", async () => {
    mockApiFetchRaw.mockResolvedValueOnce({
      blob: () => Promise.resolve(new Blob(["fake-content"])),
      headers: new Headers({
        "content-disposition": 'attachment; filename="report.pdf"',
      }),
    } as unknown as Response);

    const { result } = renderHook(() => useDocumentDownload("doc-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.downloadUrl).toBe(fakeObjectUrl);
    expect(result.current.filename).toBe("report.pdf");
    expect(mockCreateObjectURL).toHaveBeenCalledOnce();
  });

  it("revokes blob URL on unmount", async () => {
    mockApiFetchRaw.mockResolvedValueOnce({
      blob: () => Promise.resolve(new Blob(["fake-content"])),
      headers: new Headers({}),
    } as unknown as Response);

    const { result, unmount } = renderHook(() => useDocumentDownload("doc-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.downloadUrl).toBe(fakeObjectUrl));

    unmount();

    expect(mockRevokeObjectURL).toHaveBeenCalledWith(fakeObjectUrl);
  });

  it("appends filename query param when provided", async () => {
    mockApiFetchRaw.mockResolvedValueOnce({
      blob: () => Promise.resolve(new Blob()),
      headers: new Headers({}),
    } as unknown as Response);

    const { result } = renderHook(
      () => useDocumentDownload("doc-1", "my file.pdf"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockApiFetchRaw).toHaveBeenCalledWith(
      "/api/v1/documents/doc-1/download?filename=my%20file.pdf",
      expect.anything(),
    );
  });

  it("returns error when fetch fails", async () => {
    mockApiFetchRaw.mockRejectedValueOnce(new Error("Not found"));

    const { result } = renderHook(() => useDocumentDownload("doc-bad"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.downloadUrl).toBeNull();
    expect(result.current.error?.message).toBe("Not found");
  });
});
