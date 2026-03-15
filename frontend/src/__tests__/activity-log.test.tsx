import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

import { ActivityLog } from "@/components/chat/activity-log";
import type { ToolCallEntry } from "@/types";

const sampleToolCalls: ToolCallEntry[] = [
  { tool: "case_context", label: "Loaded case context" },
  { tool: "vector_search", label: "Searched documents" },
  { tool: "graph_query", label: "Queried knowledge graph" },
];

describe("ActivityLog", () => {
  it("renders nothing when not streaming and no tool calls", () => {
    const { container } = render(
      <ActivityLog toolCalls={[]} stage={null} isStreaming={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows phase label with spinner while streaming", () => {
    render(
      <ActivityLog toolCalls={[]} stage="investigating" isStreaming={true} />,
    );
    expect(screen.getByTestId("activity-log")).toBeInTheDocument();
    expect(screen.getByText("Analyzing sources")).toBeInTheDocument();
  });

  it("shows progress bar while streaming", () => {
    const { container } = render(
      <ActivityLog toolCalls={[]} stage="retrieving" isStreaming={true} />,
    );
    // 4 progress bar segments
    const bars = container.querySelectorAll(".h-1.w-8");
    expect(bars).toHaveLength(4);
  });

  it("shows completed tool calls with checkmarks during streaming", () => {
    render(
      <ActivityLog
        toolCalls={sampleToolCalls}
        stage="investigating"
        isStreaming={true}
      />,
    );
    expect(screen.getByText("Loaded case context")).toBeInTheDocument();
    expect(screen.getByText("Searched documents")).toBeInTheDocument();
    expect(screen.getByText("Queried knowledge graph")).toBeInTheDocument();
    expect(screen.getByTestId("activity-log-steps")).toBeInTheDocument();
  });

  it("shows collapsed summary after completion", () => {
    render(
      <ActivityLog
        toolCalls={sampleToolCalls}
        stage={null}
        isStreaming={false}
      />,
    );
    const toggle = screen.getByTestId("activity-log-toggle");
    expect(toggle).toBeInTheDocument();
    // Summary text should contain the joined labels
    expect(toggle.textContent).toContain("Loaded case context");
    expect(toggle.textContent).toContain("Searched documents");
    expect(toggle.textContent).toContain("Queried knowledge graph");
  });

  it("expands to show full list on click", () => {
    render(
      <ActivityLog
        toolCalls={sampleToolCalls}
        stage={null}
        isStreaming={false}
      />,
    );
    expect(screen.queryByTestId("activity-log-expanded")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("activity-log-toggle"));

    expect(screen.getByTestId("activity-log-expanded")).toBeInTheDocument();
    expect(screen.getByText("Analysis steps")).toBeInTheDocument();
    expect(screen.getByText("Loaded case context")).toBeInTheDocument();
    expect(screen.getByText("Searched documents")).toBeInTheDocument();
  });

  it("collapses back on second click", () => {
    render(
      <ActivityLog
        toolCalls={sampleToolCalls}
        stage={null}
        isStreaming={false}
      />,
    );
    const toggle = screen.getByTestId("activity-log-toggle");

    fireEvent.click(toggle);
    expect(screen.getByTestId("activity-log-expanded")).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByTestId("activity-log-expanded")).not.toBeInTheDocument();
  });

  it("maps stages to correct phases", () => {
    const { rerender } = render(
      <ActivityLog toolCalls={[]} stage="connecting" isStreaming={true} />,
    );
    expect(screen.getByText("Understanding your question")).toBeInTheDocument();

    rerender(
      <ActivityLog toolCalls={[]} stage="retrieving" isStreaming={true} />,
    );
    expect(screen.getByText("Searching documents")).toBeInTheDocument();

    rerender(
      <ActivityLog toolCalls={[]} stage="generating" isStreaming={true} />,
    );
    expect(screen.getByText("Writing response")).toBeInTheDocument();
  });
});
