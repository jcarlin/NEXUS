import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockNavigate = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  useNavigate: () => mockNavigate,
}));

vi.mock("@/hooks/use-stream-query", () => ({
  useStreamQuery: () => ({
    streamingText: "",
    sources: [],
    stage: null,
    isStreaming: false,
    citedClaims: [],
    entities: [],
    followUps: [],
    threadId: null,
    pendingUserMessage: null,
    error: null,
    lastQuery: null,
    send: vi.fn(),
    cancel: vi.fn(),
  }),
}));

vi.mock("@/components/chat/chat-layout", () => ({
  ChatLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chat-layout">{children}</div>
  ),
}));

vi.mock("@/components/chat/message-list", () => ({
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
  }: {
    onSend: (text: string) => void;
    isStreaming: boolean;
    disabled: boolean;
  }) => (
    <div data-testid="message-input" data-streaming={isStreaming} data-disabled={disabled}>
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
  });

  it("renders chat layout", () => {
    render(<Component />);
    expect(screen.getByTestId("chat-layout")).toBeInTheDocument();
  });

  it("renders message list", () => {
    render(<Component />);
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
  });

  it("renders message input", () => {
    render(<Component />);
    expect(screen.getByTestId("message-input")).toBeInTheDocument();
  });

  it("renders findings bar", () => {
    render(<Component />);
    expect(screen.getByTestId("findings-bar")).toBeInTheDocument();
  });

  it("message input is not disabled when not streaming", () => {
    render(<Component />);
    expect(screen.getByTestId("message-input")).toHaveAttribute("data-disabled", "false");
  });

  it("starts with empty messages", () => {
    render(<Component />);
    expect(screen.getByTestId("message-list")).toHaveTextContent("0 messages");
  });
});
