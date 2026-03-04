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
];

describe("CitationSidebar", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  it("does not render when closed", () => {
    render(<CitationSidebar />);
    expect(screen.queryByTestId("citation-sidebar")).not.toBeInTheDocument();
  });

  it("renders when opened with sources", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    render(<CitationSidebar />);
    expect(screen.getByTestId("citation-sidebar")).toBeInTheDocument();
    expect(screen.getByText("Sources (2)")).toBeInTheDocument();
  });

  it("shows first source as active by default", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    render(<CitationSidebar />);
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("Page 5")).toBeInTheDocument();
    expect(screen.getByText("95% relevant")).toBeInTheDocument();
  });

  it("switches active source when clicking tab", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    render(<CitationSidebar />);

    // Click the second source tab
    const tab2 = screen.getByRole("button", { name: "2" });
    fireEvent.click(tab2);

    expect(screen.getByText("email-thread.eml")).toBeInTheDocument();
    expect(screen.getByText("82% relevant")).toBeInTheDocument();
  });

  it("closes when clicking close button", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    const { rerender } = render(<CitationSidebar />);
    expect(screen.getByTestId("citation-sidebar")).toBeInTheDocument();

    // Find and click the close button in the header
    const header = screen.getByText("Sources (2)").parentElement!.parentElement!;
    const xButton = header.querySelector("button");
    if (xButton) fireEvent.click(xButton);

    rerender(<CitationSidebar />);
    expect(screen.queryByTestId("citation-sidebar")).not.toBeInTheDocument();
  });

  it("shows excerpt text for active source", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    render(<CitationSidebar />);
    expect(
      screen.getByText("The parties agreed to the terms."),
    ).toBeInTheDocument();
  });
});

describe("useCitationStore", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  it("opens with sources and sets active", () => {
    const store = useCitationStore.getState();
    store.openWithSources(MOCK_SOURCES, [], MOCK_SOURCES[1]);

    const state = useCitationStore.getState();
    expect(state.isOpen).toBe(true);
    expect(state.allSources).toHaveLength(2);
    expect(state.activeSource?.id).toBe("doc-2");
  });

  it("sets active source", () => {
    const store = useCitationStore.getState();
    store.openWithSources(MOCK_SOURCES, []);
    store.setActiveSource(MOCK_SOURCES[1]!);

    expect(useCitationStore.getState().activeSource?.id).toBe("doc-2");
  });

  it("closes and resets state", () => {
    const store = useCitationStore.getState();
    store.openWithSources(MOCK_SOURCES, []);
    store.close();

    const state = useCitationStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.allSources).toHaveLength(0);
    expect(state.activeSource).toBeNull();
  });
});
