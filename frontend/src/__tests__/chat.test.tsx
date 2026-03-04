import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act as domAct } from "@testing-library/react";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { TooltipProvider } from "@/components/ui/tooltip";

// ---- Mocks ---- //

vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Page: () => <div />,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(),
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({ accessToken: "test-token" }),
  },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({
        matterId: "matter-1",
        findings: [],
        addFinding: vi.fn(),
        removeFinding: vi.fn(),
        clearFindings: vi.fn(),
      }),
    {
      getState: () => ({ matterId: "matter-1", findings: [] }),
    },
  ),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
    search?: Record<string, unknown>;
    params?: Record<string, unknown>;
  }) => <a href={props.to}>{children}</a>,
}));

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useStreamQuery } from "@/hooks/use-stream-query";

// Wrapper for tooltip-dependent components
function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

// ---- Test 1: SSE streaming updates text state correctly ---- //

describe("SSE streaming hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates text state correctly when receiving SSE events", async () => {
    const mockFetchEventSource = vi.mocked(fetchEventSource);

    let capturedOnMessage: ((event: { data: string; event?: string }) => void) | undefined;

    mockFetchEventSource.mockImplementation(async (_url, options) => {
      const opts = options as {
        onmessage?: (event: { data: string; event?: string }) => void;
        onopen?: (response: Response) => Promise<void>;
      };

      if (opts.onopen) {
        await opts.onopen(new Response(null, { status: 200 }));
      }

      capturedOnMessage = opts.onmessage;
    });

    const { result } = renderHook(() => useStreamQuery());

    // Initial state
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.streamingText).toBe("");

    // Send a query — triggers fetchEventSource
    await act(async () => {
      result.current.send("What happened?");
    });

    // Should be streaming now with optimistic user message
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.pendingUserMessage).toBe("What happened?");
    expect(result.current.lastQuery).toBe("What happened?");
    expect(capturedOnMessage).toBeDefined();

    // Feed SSE events through the captured callback
    act(() => {
      capturedOnMessage!({ event: "status", data: JSON.stringify({ type: "status", stage: "retrieving" }) });
    });
    expect(result.current.stage).toBe("retrieving");

    act(() => {
      capturedOnMessage!({
        event: "sources",
        data: JSON.stringify({
          type: "sources",
          documents: [
            { id: "d1", filename: "memo.pdf", chunk_text: "test", relevance_score: 0.9 },
          ],
        }),
      });
    });
    expect(result.current.sources).toHaveLength(1);
    expect(result.current.sources[0]?.filename).toBe("memo.pdf");

    act(() => {
      capturedOnMessage!({ event: "token", data: JSON.stringify({ type: "token", text: "The " }) });
    });
    act(() => {
      capturedOnMessage!({ event: "token", data: JSON.stringify({ type: "token", text: "answer " }) });
    });
    act(() => {
      capturedOnMessage!({ event: "token", data: JSON.stringify({ type: "token", text: "is here." }) });
    });
    expect(result.current.streamingText).toBe("The answer is here.");

    act(() => {
      capturedOnMessage!({
        event: "done",
        data: JSON.stringify({
          type: "done",
          thread_id: "t-123",
          follow_ups: ["What about X?"],
          entities: [{ name: "Acme Corp", type: "ORGANIZATION", connections: 5 }],
          cited_claims: [],
        }),
      });
    });

    expect(result.current.threadId).toBe("t-123");
    expect(result.current.followUps).toEqual(["What about X?"]);
    expect(result.current.entities).toHaveLength(1);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.pendingUserMessage).toBeNull();
  });

  it("clears pendingUserMessage on cancel", async () => {
    const mockFetchEventSource = vi.mocked(fetchEventSource);
    mockFetchEventSource.mockImplementation(async (_url, options) => {
      const opts = options as {
        onopen?: (response: Response) => Promise<void>;
      };
      if (opts.onopen) {
        await opts.onopen(new Response(null, { status: 200 }));
      }
    });

    const { result } = renderHook(() => useStreamQuery());

    await act(async () => {
      result.current.send("Test query");
    });
    expect(result.current.pendingUserMessage).toBe("Test query");

    act(() => {
      result.current.cancel();
    });
    expect(result.current.pendingUserMessage).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });
});

// ---- Test 2: Citation marker renders [N] with tooltip ---- //

import { CitationMarker } from "@/components/chat/citation-marker";

describe("CitationMarker", () => {
  it("renders [N] with tooltip showing source info", () => {
    const source = {
      id: "doc-1",
      filename: "contract.pdf",
      page: 12,
      chunk_text: "Relevant text from the document about the agreement.",
      relevance_score: 0.92,
    };

    render(<CitationMarker index={2} source={source} />, { wrapper: Wrapper });

    // Citation marker shows 1-indexed number (index + 1 = 3)
    const marker = screen.getByText("3");
    expect(marker).toBeInTheDocument();
    expect(marker.closest("a")).toHaveAttribute("href", "/documents");
  });
});

// ---- Test 3: AssistantMessage links citations to document page ---- //

import { AssistantMessage } from "@/components/chat/assistant-message";

describe("AssistantMessage", () => {
  it("renders inline citation markers that link to documents", () => {
    const sources = [
      {
        id: "doc-a",
        filename: "deposition.pdf",
        page: 5,
        chunk_text: "Witness testimony excerpt.",
        relevance_score: 0.88,
      },
    ];

    domAct(() => {
      render(
        <AssistantMessage
          content="According to the testimony [1], the events occurred in March."
          sources={sources}
          entities={[]}
        />,
        { wrapper: Wrapper },
      );
    });

    // The [1] should be rendered as a clickable citation marker (button for quick view)
    const citationLink = screen.getByText("1");
    expect(citationLink).toBeInTheDocument();
    expect(citationLink.tagName).toBe("BUTTON");

    // Regular text should still be rendered
    expect(screen.getByText(/According to the testimony/)).toBeInTheDocument();
  });
});
