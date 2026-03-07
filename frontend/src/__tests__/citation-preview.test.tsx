import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Page: () => <div />,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("@/hooks/use-document-preview", () => ({
  useDocumentPreview: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

import { useDocumentPreview } from "@/hooks/use-document-preview";
import { CitationPreview } from "@/components/chat/citation-preview";
import type { SourceDocument } from "@/types";

const mockUseDocumentPreview = vi.mocked(useDocumentPreview);

const pdfSource: SourceDocument = {
  id: "doc-1",
  filename: "contract.pdf",
  page: 5,
  chunk_text: "The parties agreed to the terms.",
  relevance_score: 0.95,
};

const textSource: SourceDocument = {
  id: "doc-2",
  filename: "notes.txt",
  page: null,
  chunk_text: "Meeting notes from discussion.",
  relevance_score: 0.82,
  download_url: "https://example.com/notes.txt",
};

const unknownSource: SourceDocument = {
  id: "doc-3",
  filename: "archive.zip",
  page: null,
  chunk_text: "Binary content.",
  relevance_score: 0.5,
};

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

describe("CitationPreview", () => {
  const onExpandClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDocumentPreview.mockReturnValue({
      previewUrl: null,
      isLoading: false,
      error: null,
    });
  });

  it("renders thumbnail for PDF source when preview available", () => {
    mockUseDocumentPreview.mockReturnValue({
      previewUrl: "https://example.com/thumb.png",
      isLoading: false,
      error: null,
    });

    render(
      <CitationPreview
        source={pdfSource}
        allSources={[pdfSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "https://example.com/thumb.png");
  });

  it("shows skeleton while preview loading", () => {
    mockUseDocumentPreview.mockReturnValue({
      previewUrl: null,
      isLoading: true,
      error: null,
    });

    const { container } = render(
      <CitationPreview
        source={pdfSource}
        allSources={[pdfSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows fallback icon when no preview for PDF", () => {
    render(
      <CitationPreview
        source={pdfSource}
        allSources={[pdfSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    // Should show the FileText fallback icon area
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("calls onExpandClick when thumbnail clicked", () => {
    mockUseDocumentPreview.mockReturnValue({
      previewUrl: "https://example.com/thumb.png",
      isLoading: false,
      error: null,
    });

    render(
      <CitationPreview
        source={pdfSource}
        allSources={[pdfSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    const button = screen.getByRole("img").closest("button")!;
    fireEvent.click(button);
    expect(onExpandClick).toHaveBeenCalledTimes(1);
  });

  it("renders excerpt for text source", () => {
    render(
      <CitationPreview
        source={textSource}
        allSources={[textSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    expect(screen.getByText("Meeting notes from discussion.")).toBeInTheDocument();
  });

  it("renders plain excerpt for unknown type", () => {
    render(
      <CitationPreview
        source={unknownSource}
        allSources={[unknownSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    expect(screen.getByText("Binary content.")).toBeInTheDocument();
    expect(screen.getByText("Excerpt")).toBeInTheDocument();
  });

  it("shows excerpt with accent bar for PDF", () => {
    const { container } = render(
      <CitationPreview
        source={pdfSource}
        allSources={[pdfSource]}
        onExpandClick={onExpandClick}
      />,
      { wrapper: createWrapper() },
    );

    // The amber accent bar is a border-l-2 border-amber-500/60
    expect(container.querySelector(".border-amber-500\\/60")).toBeInTheDocument();
  });
});
