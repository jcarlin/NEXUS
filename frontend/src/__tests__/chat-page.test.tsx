import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockNavigate = vi.fn();
const mockSend = vi.fn();

let mockStreamState = {
  streamingText: "",
  sources: [],
  stage: null as string | null,
  isStreaming: false,
  citedClaims: [],
  entities: [],
  followUps: [],
  toolCalls: [],
  threadId: null as string | null,
  pendingUserMessage: null as string | null,
  error: null as string | null,
  lastQuery: null as string | null,
  send: mockSend,
  cancel: vi.fn(),
};

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  useNavigate: () => mockNavigate,
}));

vi.mock("@/hooks/use-stream-query", () => ({
  useStreamQuery: () => mockStreamState,
}));

vi.mock("@/components/chat/chat-layout", () => ({
  ChatLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chat-layout">{children}</div>
  ),
}));

vi.mock("@/components/chat/message-list", () => ({
  EXAMPLE_QUERIES: [
    "Who are the key parties in this matter?",
    "Summarize the timeline of events",
    "Which documents mention financial transactions?",
    "Find communications between executives",
  ],
  MessageList: ({
    messages,
    onExampleClick,
  }: {
    messages: unknown[];
    onExampleClick?: (q: string) => void;
  }) => (
    <div data-testid="message-list">
      {messages.length} messages
      {onExampleClick && <button onClick={() => onExampleClick("test")}>Example</button>}
    </div>
  ),
}));

vi.mock("@/components/chat/message-input", () => ({
  MessageInput: ({
    onSend,
    isStreaming,
    disabled,
    variant,
  }: {
    onSend: (text: string) => void;
    isStreaming: boolean;
    disabled: boolean;
    variant?: string;
  }) => (
    <div
      data-testid="message-input"
      data-streaming={isStreaming}
      data-disabled={disabled}
      data-variant={variant ?? "default"}
    >
      <button onClick={() => onSend("test query")}>Send</button>
    </div>
  ),
}));

vi.mock("@/components/chat/findings-bar", () => ({
  FindingsBar: () => <div data-testid="findings-bar">Findings</div>,
}));

import { Route } from "@/routes/chat/index.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("ChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStreamState = {
      streamingText: "",
      sources: [],
      stage: null,
      isStreaming: false,
      citedClaims: [],
      entities: [],
      followUps: [],
      toolCalls: [],
      threadId: null,
      pendingUserMessage: null,
      error: null,
      lastQuery: null,
      send: mockSend,
      cancel: vi.fn(),
    };
  });

  it("renders chat layout", () => {
    render(<Component />);
    expect(screen.getByTestId("chat-layout")).toBeInTheDocument();
  });

  describe("welcome state (empty)", () => {
    it("shows welcome text when no content", () => {
      render(<Component />);
      expect(screen.getByText("Welcome to NEXUS")).toBeInTheDocument();
      expect(screen.getByText("Your legal investigation assistant")).toBeInTheDocument();
    });

    it("shows example query buttons", () => {
      render(<Component />);
      expect(screen.getByText("Who are the key parties in this matter?")).toBeInTheDocument();
      expect(screen.getByText("Summarize the timeline of events")).toBeInTheDocument();
    });

    it("renders message input with standalone variant", () => {
      render(<Component />);
      expect(screen.getByTestId("message-input")).toHaveAttribute("data-variant", "standalone");
    });

    it("does not render message list or findings bar", () => {
      render(<Component />);
      expect(screen.queryByTestId("message-list")).not.toBeInTheDocument();
      expect(screen.queryByTestId("findings-bar")).not.toBeInTheDocument();
    });

    it("sends query when example button is clicked", () => {
      render(<Component />);
      fireEvent.click(screen.getByText("Who are the key parties in this matter?"));
      expect(mockSend).toHaveBeenCalledWith("Who are the key parties in this matter?");
    });
  });

  describe("active state (has content)", () => {
    beforeEach(() => {
      mockStreamState.pendingUserMessage = "test query";
    });

    it("renders message list when content exists", () => {
      render(<Component />);
      expect(screen.getByTestId("message-list")).toBeInTheDocument();
    });

    it("renders findings bar", () => {
      render(<Component />);
      expect(screen.getByTestId("findings-bar")).toBeInTheDocument();
    });

    it("renders message input with default variant", () => {
      render(<Component />);
      expect(screen.getByTestId("message-input")).toHaveAttribute("data-variant", "default");
    });

    it("does not show welcome text", () => {
      render(<Component />);
      expect(screen.queryByText("Welcome to NEXUS")).not.toBeInTheDocument();
    });
  });

  it("switches to active layout when streaming", () => {
    mockStreamState.isStreaming = true;
    render(<Component />);
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
    expect(screen.queryByText("Welcome to NEXUS")).not.toBeInTheDocument();
  });

  it("message input is not disabled when not streaming", () => {
    render(<Component />);
    expect(screen.getByTestId("message-input")).toHaveAttribute("data-disabled", "false");
  });
});
