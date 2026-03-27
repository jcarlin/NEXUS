import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

// Mock child components that have complex dependencies
vi.mock("@/components/chat/assistant-message", () => ({
  AssistantMessage: ({
    content,
    isStreaming,
  }: {
    content: string;
    isStreaming?: boolean;
  }) => (
    <div data-testid="assistant-message" data-streaming={isStreaming}>
      {content}
    </div>
  ),
}));

vi.mock("@/components/chat/user-message", () => ({
  UserMessage: ({ content }: { content: string }) => (
    <div data-testid="user-message">{content}</div>
  ),
}));

vi.mock("@/components/chat/activity-log", () => ({
  ActivityLog: ({
    toolCalls,
    stage,
    isStreaming,
  }: {
    toolCalls: { tool: string; label: string }[];
    stage: string | null;
    isStreaming: boolean;
  }) => (
    <div
      data-testid="activity-log"
      data-stage={stage}
      data-streaming={isStreaming}
    >
      {toolCalls.map((tc: { tool: string; label: string }, i: number) => (
        <span key={i}>{tc.label}</span>
      ))}
    </div>
  ),
}));

vi.mock("@/components/chat/error-message", () => ({
  ErrorMessage: ({
    message,
    onRetry,
  }: {
    message: string;
    onRetry: () => void;
  }) => (
    <div data-testid="error-message">
      <span>{message}</span>
      <button onClick={onRetry}>Try again</button>
    </div>
  ),
}));

vi.mock("@/components/chat/follow-up-chips", () => ({
  FollowUpChips: ({
    questions,
    onSelect,
  }: {
    questions: string[];
    onSelect: (q: string) => void;
  }) => (
    <div data-testid="follow-up-chips">
      {questions.map((q) => (
        <button key={q} onClick={() => onSelect(q)}>
          {q}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: React.forwardRef(
    (
      { children, ...props }: { children: React.ReactNode },
      ref: React.Ref<HTMLDivElement>,
    ) => (
      <div ref={ref} data-testid="scroll-area" {...props}>
        {children}
      </div>
    ),
  ),
}));

// Mock scrollIntoView since jsdom doesn't support it
Element.prototype.scrollIntoView = vi.fn();

import { MessageList } from "@/components/chat/message-list";
import type { ChatMessage } from "@/types";

const makeUserMessage = (content: string): ChatMessage => ({
  role: "user",
  content,
  source_documents: [],
  entities_mentioned: [],
  follow_up_questions: [],
  cited_claims: [],
  timestamp: new Date().toISOString(),
});

const makeAssistantMessage = (content: string): ChatMessage => ({
  role: "assistant",
  content,
  source_documents: [
    {
      id: "src-1",
      filename: "test.pdf",
      page: 1,
      chunk_text: "test chunk",
      relevance_score: 0.9,
    },
  ],
  entities_mentioned: [],
  follow_up_questions: [],
  cited_claims: [],
  timestamp: new Date().toISOString(),
});

describe("MessageList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows empty state when no messages", () => {
    render(<MessageList messages={[]} />);
    expect(screen.getByText("Welcome to NEXUS")).toBeInTheDocument();
  });

  it("shows description text in empty state", () => {
    render(<MessageList messages={[]} />);
    expect(
      screen.getByText(/Ask questions about documents/),
    ).toBeInTheDocument();
  });

  it("shows example queries when onExampleClick is provided", () => {
    const onExampleClick = vi.fn();
    render(<MessageList messages={[]} onExampleClick={onExampleClick} />);
    expect(
      screen.getByText("Who are the key parties in this matter?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Summarize the timeline of events"),
    ).toBeInTheDocument();
  });

  it("calls onExampleClick when an example is clicked", () => {
    const onExampleClick = vi.fn();
    render(<MessageList messages={[]} onExampleClick={onExampleClick} />);
    fireEvent.click(
      screen.getByText("Who are the key parties in this matter?"),
    );
    expect(onExampleClick).toHaveBeenCalledWith(
      "Who are the key parties in this matter?",
    );
  });

  it("does not show example queries when onExampleClick is not provided", () => {
    render(<MessageList messages={[]} />);
    expect(
      screen.queryByText("Who are the key parties in this matter?"),
    ).not.toBeInTheDocument();
  });

  it("renders user messages", () => {
    render(
      <MessageList messages={[makeUserMessage("Hello there")]} />,
    );
    expect(screen.getByTestId("user-message")).toHaveTextContent(
      "Hello there",
    );
  });

  it("renders assistant messages", () => {
    render(
      <MessageList
        messages={[makeAssistantMessage("Here is my response")]}
      />,
    );
    expect(screen.getByTestId("assistant-message")).toHaveTextContent(
      "Here is my response",
    );
  });

  it("renders multiple messages in order", () => {
    render(
      <MessageList
        messages={[
          makeUserMessage("Question 1"),
          makeAssistantMessage("Answer 1"),
          makeUserMessage("Question 2"),
        ]}
      />,
    );
    const userMsgs = screen.getAllByTestId("user-message");
    expect(userMsgs).toHaveLength(2);
    expect(screen.getAllByTestId("assistant-message")).toHaveLength(1);
  });

  it("shows ActivityLog when stage is set", () => {
    render(<MessageList messages={[]} stage="retrieving" />);
    const log = screen.getByTestId("activity-log");
    expect(log).toHaveAttribute("data-stage", "retrieving");
    expect(log).toHaveAttribute("data-streaming", "true");
  });

  it("shows ActivityLog alongside streaming text", () => {
    render(
      <MessageList
        messages={[]}
        stage="generating"
        streaming={{
          text: "Some partial text",
          sources: [],
          entities: [],
          citedClaims: [],
          toolCalls: [{ tool: "vector_search", label: "Searched documents" }],
          traceSteps: [],
          traceSummary: null,
        }}
      />,
    );
    expect(screen.getByTestId("activity-log")).toBeInTheDocument();
    expect(screen.getByText("Searched documents")).toBeInTheDocument();
  });

  it("shows streaming assistant message when streaming is set", () => {
    render(
      <MessageList
        messages={[]}
        streaming={{
          text: "Streaming text...",
          sources: [],
          entities: [],
          citedClaims: [],
          toolCalls: [],
          traceSteps: [],
          traceSummary: null,
        }}
      />,
    );
    const assistantMsg = screen.getByTestId("assistant-message");
    expect(assistantMsg).toHaveTextContent("Streaming text...");
    expect(assistantMsg).toHaveAttribute("data-streaming", "true");
  });

  it("shows error with retry button", () => {
    const onRetry = vi.fn();
    render(
      <MessageList
        messages={[]}
        error="Something went wrong"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByTestId("error-message")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Try again"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not show error message when no error", () => {
    render(<MessageList messages={[]} />);
    expect(screen.queryByTestId("error-message")).not.toBeInTheDocument();
  });

  it("shows follow-up chips when not streaming", () => {
    const onFollowUpSelect = vi.fn();
    render(
      <MessageList
        messages={[makeAssistantMessage("Response")]}
        followUps={["Follow up 1", "Follow up 2"]}
        onFollowUpSelect={onFollowUpSelect}
      />,
    );
    expect(screen.getByTestId("follow-up-chips")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Follow up 1"));
    expect(onFollowUpSelect).toHaveBeenCalledWith("Follow up 1");
  });

  it("does not show follow-up chips when streaming", () => {
    render(
      <MessageList
        messages={[]}
        followUps={["Follow up 1"]}
        onFollowUpSelect={vi.fn()}
        streaming={{
          text: "Still streaming...",
          sources: [],
          entities: [],
          citedClaims: [],
          toolCalls: [],
          traceSteps: [],
          traceSummary: null,
        }}
      />,
    );
    expect(screen.queryByTestId("follow-up-chips")).not.toBeInTheDocument();
  });

  it("hides empty state when there are messages", () => {
    render(
      <MessageList messages={[makeUserMessage("Hi")]} />,
    );
    expect(
      screen.queryByText("Welcome to NEXUS"),
    ).not.toBeInTheDocument();
  });

  it("shows pending user message", () => {
    render(
      <MessageList messages={[]} pendingUserMessage="Pending question" />,
    );
    expect(screen.getByTestId("user-message")).toHaveTextContent(
      "Pending question",
    );
  });

  it("shows activity log for saved assistant messages with tool_calls", () => {
    const msg: ChatMessage = {
      ...makeAssistantMessage("Response with tools"),
      tool_calls: [
        { tool: "vector_search", label: "Searched documents" },
        { tool: "graph_query", label: "Queried knowledge graph" },
      ],
    };
    render(<MessageList messages={[msg]} />);
    const log = screen.getByTestId("activity-log");
    expect(log).toBeInTheDocument();
    expect(log).toHaveAttribute("data-streaming", "false");
    expect(screen.getByText("Searched documents")).toBeInTheDocument();
    expect(screen.getByText("Queried knowledge graph")).toBeInTheDocument();
  });

  it("does not show activity log for saved messages without tool_calls", () => {
    render(
      <MessageList messages={[makeAssistantMessage("No tools used")]} />,
    );
    expect(screen.queryByTestId("activity-log")).not.toBeInTheDocument();
  });
});
