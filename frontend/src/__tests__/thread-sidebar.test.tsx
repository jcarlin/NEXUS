import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, unknown>;
  }) => <a href={props.to}>{children}</a>,
  useParams: () => ({}),
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1" }),
    {
      getState: () => ({ matterId: "matter-1" }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

const mockUseQuery = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import { ThreadSidebar } from "@/components/chat/thread-sidebar";

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

describe("ThreadSidebar", () => {
  const onToggle = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  describe("collapsed mode", () => {
    it("shows expand button", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed onToggle={onToggle} />
        </Wrapper>,
      );
      // Collapsed mode has the ChevronsRight button for expanding
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });

    it("clicking expand button calls onToggle", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed onToggle={onToggle} />
        </Wrapper>,
      );
      const buttons = screen.getAllByRole("button");
      // First button is the expand toggle
      fireEvent.click(buttons[0]!);
      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it("shows new chat link in collapsed mode", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed onToggle={onToggle} />
        </Wrapper>,
      );
      const links = screen.getAllByRole("link");
      const chatLink = links.find((l) => l.getAttribute("href") === "/chat");
      expect(chatLink).toBeDefined();
    });

    it("does not show 'Chat History' header in collapsed mode", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed onToggle={onToggle} />
        </Wrapper>,
      );
      expect(screen.queryByText("Chat History")).not.toBeInTheDocument();
    });
  });

  describe("expanded mode", () => {
    it("shows 'Chat History' header", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      expect(screen.getByText("Chat History")).toBeInTheDocument();
    });

    it("shows 'New' button", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      expect(screen.getByText("New")).toBeInTheDocument();
    });

    it("shows collapse button", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      // There should be a collapse button (ChevronsLeft)
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });

    it("shows 'No conversations yet' when empty and not loading", () => {
      mockUseQuery.mockReturnValue({
        data: { threads: [] },
        isLoading: false,
      });
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      expect(screen.getByText("No conversations yet")).toBeInTheDocument();
    });

    it("shows loading spinner when loading", () => {
      mockUseQuery.mockReturnValue({
        data: undefined,
        isLoading: true,
      });
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      // The loader is an SVG with animate-spin
      expect(screen.queryByText("No conversations yet")).not.toBeInTheDocument();
    });

    it("renders threads when data is available", () => {
      const now = new Date();
      mockUseQuery.mockReturnValue({
        data: {
          threads: [
            {
              thread_id: "t-1",
              message_count: 5,
              last_message_at: now.toISOString(),
              first_query: "What happened in the case?",
            },
          ],
        },
        isLoading: false,
      });
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      expect(
        screen.getByText("What happened in the case?"),
      ).toBeInTheDocument();
      expect(screen.getByText("5 messages")).toBeInTheDocument();
    });

    it("groups threads by time periods", () => {
      const now = new Date();
      const yesterday = new Date(now.getTime() - 86400000 - 1000);
      const weekAgo = new Date(now.getTime() - 3 * 86400000);
      const monthAgo = new Date(now.getTime() - 30 * 86400000);

      mockUseQuery.mockReturnValue({
        data: {
          threads: [
            {
              thread_id: "t-1",
              message_count: 2,
              last_message_at: now.toISOString(),
              first_query: "Today thread",
            },
            {
              thread_id: "t-2",
              message_count: 3,
              last_message_at: yesterday.toISOString(),
              first_query: "Yesterday thread",
            },
            {
              thread_id: "t-3",
              message_count: 4,
              last_message_at: weekAgo.toISOString(),
              first_query: "This week thread",
            },
            {
              thread_id: "t-4",
              message_count: 1,
              last_message_at: monthAgo.toISOString(),
              first_query: "Older thread",
            },
          ],
        },
        isLoading: false,
      });

      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );

      expect(screen.getByText("Today")).toBeInTheDocument();
      expect(screen.getByText("Yesterday")).toBeInTheDocument();
      expect(screen.getByText("This Week")).toBeInTheDocument();
      expect(screen.getByText("Older")).toBeInTheDocument();
    });

    it("clicking collapse button calls onToggle", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      // Find the collapse button (last button in header area)
      const buttons = screen.getAllByRole("button");
      // Click the last button which should be the collapse toggle
      const collapseBtn = buttons[buttons.length - 1]!;
      fireEvent.click(collapseBtn);
      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it("'New' button links to /chat", () => {
      render(
        <Wrapper>
          <ThreadSidebar collapsed={false} onToggle={onToggle} />
        </Wrapper>,
      );
      const newLink = screen.getByText("New").closest("a");
      expect(newLink).toHaveAttribute("href", "/chat");
    });
  });
});
