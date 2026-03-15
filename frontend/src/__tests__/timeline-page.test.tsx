import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
  }) => <a href={props.to}>{children}</a>,
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/analytics/timeline-view", () => ({
  TimelineView: ({ events, loading }: { events: unknown[]; loading?: boolean }) => (
    <div data-testid="timeline-view" data-loading={loading}>
      {events.length} events
    </div>
  ),
}));

import { Route } from "@/routes/analytics/timeline.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("TimelinePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Timeline heading", () => {
    render(<Component />);
    expect(screen.getByText("Timeline")).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<Component />);
    expect(
      screen.getByText("Chronological view of events for an entity."),
    ).toBeInTheDocument();
  });

  it("renders entity name input", () => {
    render(<Component />);
    expect(screen.getByLabelText("Entity name")).toBeInTheDocument();
  });

  it("renders start and end date inputs", () => {
    render(<Component />);
    expect(screen.getByLabelText("Start date")).toBeInTheDocument();
    expect(screen.getByLabelText("End date")).toBeInTheDocument();
  });

  it("shows prompt when no entity entered", () => {
    render(<Component />);
    expect(
      screen.getByText("Enter an entity name above to view their timeline of events."),
    ).toBeInTheDocument();
  });

  it("shows timeline view when entity is entered", () => {
    render(<Component />);
    fireEvent.change(screen.getByLabelText("Entity name"), {
      target: { value: "John Smith" },
    });
    expect(screen.getByTestId("timeline-view")).toBeInTheDocument();
  });
});
