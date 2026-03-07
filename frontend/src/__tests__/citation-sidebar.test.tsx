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
}));

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="resizable-group">{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizableHandle: () => <div />,
}));

import { TooltipProvider } from "@/components/ui/tooltip";
import { useCitationStore } from "@/stores/citation-store";
import { useAppStore } from "@/stores/app-store";
import { CitationSidebar } from "@/components/chat/citation-sidebar";
import { ChatHeader } from "@/components/chat/chat-header";
import { ChatLayout } from "@/components/chat/chat-layout";
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

describe("ChatLayout citation panel", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  it("does not render citation sidebar when store is closed", () => {
    render(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat content</div>
        </ChatLayout>
      </TooltipProvider>,
    );
    expect(screen.queryByTestId("citation-sidebar")).not.toBeInTheDocument();
  });

  it("renders citation sidebar when store is open with sources", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    render(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat content</div>
        </ChatLayout>
      </TooltipProvider>,
    );
    expect(screen.getByTestId("citation-sidebar")).toBeInTheDocument();
    expect(screen.getByText("Sources (2)")).toBeInTheDocument();
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

  it("toggle hides sidebar but preserves sources", () => {
    const store = useCitationStore.getState();
    store.openWithSources(MOCK_SOURCES, []);
    expect(useCitationStore.getState().isOpen).toBe(true);

    store.toggle();
    const after = useCitationStore.getState();
    expect(after.isOpen).toBe(false);
    expect(after.allSources).toHaveLength(2);
    expect(after.activeSource).not.toBeNull();
  });

  it("toggle reopens sidebar when sources exist", () => {
    const store = useCitationStore.getState();
    store.openWithSources(MOCK_SOURCES, []);
    store.toggle(); // close
    store.toggle(); // reopen

    const state = useCitationStore.getState();
    expect(state.isOpen).toBe(true);
    expect(state.allSources).toHaveLength(2);
  });

  it("toggle is a no-op when closed with no sources", () => {
    const store = useCitationStore.getState();
    store.toggle();

    expect(useCitationStore.getState().isOpen).toBe(false);
  });
});

describe("ChatHeader", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
  });

  const renderHeader = () =>
    render(
      <TooltipProvider>
        <ChatHeader />
      </TooltipProvider>,
    );

  it("renders toggle button", () => {
    renderHeader();
    expect(screen.getByRole("button", { name: "Toggle citation sidebar" })).toBeInTheDocument();
  });

  it("button is disabled when no sources loaded", () => {
    renderHeader();
    expect(screen.getByRole("button", { name: "Toggle citation sidebar" })).toBeDisabled();
  });

  it("button is enabled when sources are loaded", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    renderHeader();
    expect(screen.getByRole("button", { name: "Toggle citation sidebar" })).toBeEnabled();
  });

  it("calls toggle on click", () => {
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    renderHeader();

    const btn = screen.getByRole("button", { name: "Toggle citation sidebar" });
    fireEvent.click(btn);
    expect(useCitationStore.getState().isOpen).toBe(false);

    fireEvent.click(btn);
    expect(useCitationStore.getState().isOpen).toBe(true);
  });
});

describe("app-store deterministic setters", () => {
  it("setSidebarCollapsed sets exact value", () => {
    const store = useAppStore.getState();
    store.setSidebarCollapsed(true);
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);

    store.setSidebarCollapsed(false);
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);

    store.setSidebarCollapsed(false);
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
  });

  it("setThreadSidebarCollapsed sets exact value", () => {
    const store = useAppStore.getState();
    store.setThreadSidebarCollapsed(true);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);

    store.setThreadSidebarCollapsed(false);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);

    store.setThreadSidebarCollapsed(false);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);
  });
});

describe("ChatLayout sidebar auto-collapse", () => {
  beforeEach(() => {
    useCitationStore.getState().close();
    useAppStore.getState().setSidebarCollapsed(false);
    useAppStore.getState().setThreadSidebarCollapsed(false);
  });

  it("collapses both sidebars when citation sidebar opens", () => {
    const { rerender } = render(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);

    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    rerender(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);
  });

  it("restores previous sidebar states when citation sidebar closes", () => {
    // Start with sidebars expanded
    useAppStore.getState().setSidebarCollapsed(false);
    useAppStore.getState().setThreadSidebarCollapsed(false);

    const { rerender } = render(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    // Open citation sidebar
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    rerender(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(true);

    // Close citation sidebar
    useCitationStore.getState().close();
    rerender(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(false);
  });

  it("preserves already-collapsed state on restore", () => {
    // Start with both sidebars already collapsed
    useAppStore.getState().setSidebarCollapsed(true);
    useAppStore.getState().setThreadSidebarCollapsed(true);

    const { rerender } = render(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    // Open citation sidebar
    useCitationStore.getState().openWithSources(MOCK_SOURCES, []);
    rerender(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);

    // Close citation sidebar — should restore to collapsed (previous state)
    useCitationStore.getState().close();
    rerender(
      <TooltipProvider>
        <ChatLayout>
          <div>Chat</div>
        </ChatLayout>
      </TooltipProvider>,
    );

    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
    expect(useAppStore.getState().threadSidebarCollapsed).toBe(true);
  });
});
