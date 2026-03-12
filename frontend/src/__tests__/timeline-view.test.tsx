import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { TimelineView } from "@/components/analytics/timeline-view";
import type { TimelineEvent } from "@/types";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, unknown>;
  }) => (
    <a href={props.to} data-params={JSON.stringify(props.params)}>
      {children}
    </a>
  ),
}));

const MOCK_EVENTS: TimelineEvent[] = [
  {
    date: "2024-01-15",
    description: "Meeting with legal team",
    entities: ["John Smith", "Acme Corp"],
    document_source: "doc-1",
  },
  {
    date: "2024-02-01",
    description: "Contract signed",
    entities: [],
    document_source: null,
  },
  {
    date: null,
    description: "Undated event",
    entities: ["Jane Doe"],
    document_source: null,
  },
];

describe("TimelineView", () => {
  it("renders events", () => {
    render(<TimelineView events={MOCK_EVENTS} />);
    expect(screen.getByText("Meeting with legal team")).toBeInTheDocument();
    expect(screen.getByText("Contract signed")).toBeInTheDocument();
    expect(screen.getByText("Undated event")).toBeInTheDocument();
  });

  it("renders entity badges", () => {
    render(<TimelineView events={MOCK_EVENTS} />);
    expect(screen.getByText("John Smith")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
  });

  it("renders source document links", () => {
    render(<TimelineView events={MOCK_EVENTS} />);
    const link = screen.getByText("View source document").closest("a");
    expect(link).toHaveAttribute("href", "/documents/$id");
    expect(link).toHaveAttribute(
      "data-params",
      JSON.stringify({ id: "doc-1" }),
    );
  });

  it("does not show source link for events without document_source", () => {
    render(
      <TimelineView
        events={[{ description: "No source", entities: [], document_source: null }]}
      />,
    );
    expect(screen.queryByText("View source document")).not.toBeInTheDocument();
  });

  it("shows empty state when no events", () => {
    render(<TimelineView events={[]} />);
    expect(
      screen.getByText("No events found for the selected filters."),
    ).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    const { container } = render(<TimelineView events={[]} loading />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
