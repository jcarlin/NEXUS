import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Page: () => <div />,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
    search?: Record<string, unknown>;
  }) => <a href={props.to}>{children}</a>,
  useParams: () => ({}),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: [], isLoading: false }),
  useQueryClient: () => ({ prefetchQuery: vi.fn() }),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/hooks/use-document-download", () => ({
  useDocumentDownload: vi.fn().mockReturnValue({
    downloadUrl: "https://example.com/doc.pdf",
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/hooks/use-document-preview", () => ({
  useDocumentPreview: vi.fn().mockReturnValue({
    previewUrl: null,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/components/documents/document-viewer", () => ({
  DocumentViewer: ({
    url,
    highlightText,
    initialPage,
  }: {
    url: string;
    highlightText?: string;
    initialPage?: number;
  }) => (
    <div data-testid="document-viewer" data-url={url} data-highlight={highlightText} data-page={initialPage}>
      Document Viewer
    </div>
  ),
}));

import { useCitationStore } from "@/stores/citation-store";
import { CitationSidebar } from "@/components/chat/citation-sidebar";
import type { SourceDocument } from "@/types";

const MOCK_SOURCES: SourceDocument[] = [
  {
    id: "doc-1",
    filename: "contract.pdf",
    page: 5,
    chunk_text: "The parties agreed to the terms.",
    relevance_score: 0.95,
  },
  {
    id: "doc-2",
    filename: "email-thread.eml",
    page: null,
    chunk_text: "Discussed the merger timeline.",
    relevance_score: 0.82,
  },
  {
    id: "doc-3",
    filename: "memo.pdf",
    page: 1,
    chunk_text: "Internal memo regarding compliance.",
    relevance_score: 0.78,
  },
];

describe("Expanded citation view", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  function openExpanded() {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    useCitationStore.getState().expandView();
  }

  it("renders expanded view when mode is expanded", () => {
    openExpanded();
    render(<CitationSidebar />);

    expect(screen.getByTestId("citation-sidebar")).toHaveAttribute("data-mode", "expanded");
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("Back")).toBeInTheDocument();
  });

  it("shows DocumentViewer with highlight text", () => {
    openExpanded();
    render(<CitationSidebar />);

    const viewer = screen.getByTestId("document-viewer");
    expect(viewer).toHaveAttribute("data-highlight", "The parties agreed to the terms.");
    expect(viewer).toHaveAttribute("data-url", "https://example.com/doc.pdf");
  });

  it("shows citation count", () => {
    openExpanded();
    render(<CitationSidebar />);

    expect(screen.getByText("Citation 1 of 3")).toBeInTheDocument();
  });

  it("navigates to next source with Next button", () => {
    openExpanded();
    render(<CitationSidebar />);

    const nextButtons = screen.getAllByRole("button", { name: /next/i });
    fireEvent.click(nextButtons[0]!);

    expect(screen.getByText("email-thread.eml")).toBeInTheDocument();
    expect(screen.getByText("Citation 2 of 3")).toBeInTheDocument();
  });

  it("navigates to previous source with Prev button", () => {
    openExpanded();
    // Navigate to second source first
    useCitationStore.getState().setActiveSource(MOCK_SOURCES[1]!);
    render(<CitationSidebar />);

    expect(screen.getByText("Citation 2 of 3")).toBeInTheDocument();

    const prevButtons = screen.getAllByRole("button", { name: /prev/i });
    fireEvent.click(prevButtons[0]!);

    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("Citation 1 of 3")).toBeInTheDocument();
  });

  it("disables Prev on first source", () => {
    openExpanded();
    render(<CitationSidebar />);

    const prevButtons = screen.getAllByRole("button", { name: /prev/i });
    // The footer prev button
    expect(prevButtons[prevButtons.length - 1]).toBeDisabled();
  });

  it("disables Next on last source", () => {
    openExpanded();
    useCitationStore.getState().setActiveSource(MOCK_SOURCES[2]!);
    render(<CitationSidebar />);

    const nextButtons = screen.getAllByRole("button", { name: /next/i });
    expect(nextButtons[nextButtons.length - 1]).toBeDisabled();
  });

  it("collapses to compact view on Back button", () => {
    openExpanded();
    const { rerender } = render(<CitationSidebar />);

    fireEvent.click(screen.getByText("Back"));
    rerender(<CitationSidebar />);

    expect(useCitationStore.getState().mode).toBe("compact");
    // Should render compact mode (no data-mode="expanded")
    const sidebar = screen.getByTestId("citation-sidebar");
    expect(sidebar.getAttribute("data-mode")).toBeNull();
  });

  it("collapses on Escape key", () => {
    openExpanded();
    render(<CitationSidebar />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(useCitationStore.getState().mode).toBe("compact");
  });

  it("navigates with arrow keys", () => {
    openExpanded();
    render(<CitationSidebar />);

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(useCitationStore.getState().activeSource?.id).toBe("doc-2");

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(useCitationStore.getState().activeSource?.id).toBe("doc-3");

    // Should not go past last
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(useCitationStore.getState().activeSource?.id).toBe("doc-3");

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(useCitationStore.getState().activeSource?.id).toBe("doc-2");
  });

  it("closes sidebar from expanded mode", () => {
    openExpanded();
    const { rerender } = render(<CitationSidebar />);

    // The close() action is called by the store
    useCitationStore.getState().close();

    rerender(<CitationSidebar />);
    expect(useCitationStore.getState().isOpen).toBe(false);
    expect(useCitationStore.getState().mode).toBe("compact");
  });

  it("shows excerpt in footer with accent bar", () => {
    openExpanded();
    render(<CitationSidebar />);

    expect(screen.getByText("The parties agreed to the terms.")).toBeInTheDocument();
  });
});

describe("Citation store mode actions", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  it("expandView sets mode to expanded", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    useCitationStore.getState().expandView();
    expect(useCitationStore.getState().mode).toBe("expanded");
  });

  it("collapseView sets mode to compact", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    useCitationStore.getState().expandView();
    useCitationStore.getState().collapseView();
    expect(useCitationStore.getState().mode).toBe("compact");
  });

  it("close resets mode to compact", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    useCitationStore.getState().expandView();
    useCitationStore.getState().close();
    expect(useCitationStore.getState().mode).toBe("compact");
  });

  it("defaults to compact mode", () => {
    expect(useCitationStore.getState().mode).toBe("compact");
  });
});
