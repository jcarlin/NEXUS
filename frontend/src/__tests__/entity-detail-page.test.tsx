import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => {
    routeOptions._useParams = () => ({ id: "John%20Smith" });
    return routeOptions;
  },
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
  }) => <a href={props.to}>{children}</a>,
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

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/entities/entity-header", () => ({
  EntityHeader: ({ entity }: { entity: { name: string; type: string } }) => (
    <div data-testid="entity-header">{entity.name} ({entity.type})</div>
  ),
}));

vi.mock("@/components/entities/connections-graph", () => ({
  ConnectionsGraph: () => <div data-testid="connections-graph">Graph</div>,
}));

vi.mock("@/components/entities/document-mentions", () => ({
  DocumentMentions: ({ entityName }: { entityName: string }) => (
    <div data-testid="document-mentions">{entityName}</div>
  ),
}));

vi.mock("@/components/entities/entity-timeline", () => ({
  EntityTimeline: () => <div data-testid="entity-timeline">Timeline</div>,
}));

vi.mock("@/components/entities/reporting-chain", () => ({
  ReportingChain: () => <div data-testid="reporting-chain">Chain</div>,
}));

import { Route } from "@/routes/entities/$id";

const routeObj = Route as unknown as {
  component: React.ComponentType;
  useParams: () => { id: string };
};
routeObj.useParams = () => ({ id: "John%20Smith" });

const Component = routeObj.component;

describe("EntityDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, error: null });
  });

  it("shows loading skeletons when loading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = render(<Component />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state when query fails", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Not found"),
    });
    render(<Component />);
    expect(screen.getByText("Failed to load entity details.")).toBeInTheDocument();
  });

  it("shows 'Back to Entities' link on error", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    });
    render(<Component />);
    expect(screen.getByText("Back to Entities")).toBeInTheDocument();
  });

  it("renders entity header when data loaded", () => {
    mockUseQuery.mockReturnValue({
      data: {
        entity: { name: "John Smith", type: "person", aliases: [], mention_count: 42 },
        connections: [],
      },
      isLoading: false,
      error: null,
    });
    render(<Component />);
    expect(screen.getByTestId("entity-header")).toHaveTextContent("John Smith (person)");
  });

  it("renders connections graph", () => {
    mockUseQuery.mockReturnValue({
      data: {
        entity: { name: "John Smith", type: "person", aliases: [], mention_count: 42 },
        connections: [{ source: "John Smith", target: "Acme", relationship_type: "works_at", weight: 1 }],
      },
      isLoading: false,
      error: null,
    });
    render(<Component />);
    expect(screen.getByTestId("connections-graph")).toBeInTheDocument();
  });

  it("renders entity timeline", () => {
    mockUseQuery.mockReturnValue({
      data: {
        entity: { name: "John Smith", type: "person", aliases: [], mention_count: 42 },
        connections: [],
      },
      isLoading: false,
      error: null,
    });
    render(<Component />);
    expect(screen.getByTestId("entity-timeline")).toBeInTheDocument();
  });

  it("renders document mentions", () => {
    mockUseQuery.mockReturnValue({
      data: {
        entity: { name: "John Smith", type: "person", aliases: [], mention_count: 42 },
        connections: [],
      },
      isLoading: false,
      error: null,
    });
    render(<Component />);
    expect(screen.getByTestId("document-mentions")).toHaveTextContent("John Smith");
  });
});
