import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
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

// Mock dashboard child components
vi.mock("@/components/dashboard/recent-activity", () => ({
  RecentActivity: () => <div data-testid="recent-activity">Recent Activity</div>,
}));

vi.mock("@/components/dashboard/pipeline-status", () => ({
  PipelineStatus: () => <div data-testid="pipeline-status">Pipeline Status</div>,
}));

vi.mock("@/components/dashboard/graph-overview", () => ({
  GraphOverview: () => <div data-testid="graph-overview">Graph Overview</div>,
}));

// Track useQuery calls
const mockUseQuery = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

// Import after mocks so the route file picks up mocked dependencies
import { Route } from "@/routes/index";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Dashboard heading", () => {
    render(<Component />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders overview description", () => {
    render(<Component />);
    expect(
      screen.getByText("Overview of your investigation workspace."),
    ).toBeInTheDocument();
  });

  it("renders 4 StatCards with correct titles", () => {
    render(<Component />);
    expect(screen.getByText("Documents")).toBeInTheDocument();
    expect(screen.getByText("Entities")).toBeInTheDocument();
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("shows 0 values when queries return no data", () => {
    render(<Component />);
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBeGreaterThanOrEqual(4);
  });

  it("shows correct values when queries return data", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "doc-count") {
        return { data: { items: [], total: 42 }, isLoading: false };
      }
      if (key === "graph-stats-summary") {
        return {
          data: { total_nodes: 135, total_edges: 387, node_counts: {} },
          isLoading: false,
        };
      }
      if (key === "active-jobs") {
        return { data: { items: [], total: 3 }, isLoading: false };
      }
      if (key === "hot-doc-count") {
        return { data: { items: [], total: 7 }, isLoading: false };
      }
      return { data: undefined, isLoading: false };
    });

    render(<Component />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("135")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders sub-components for bottom section", () => {
    render(<Component />);
    expect(screen.getByTestId("recent-activity")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-status")).toBeInTheDocument();
    expect(screen.getByTestId("graph-overview")).toBeInTheDocument();
  });

  it("shows descriptions for each stat card", () => {
    render(<Component />);
    expect(screen.getByText("Total ingested")).toBeInTheDocument();
    expect(screen.getByText("In knowledge graph")).toBeInTheDocument();
    expect(screen.getByText("Score >= 0.7")).toBeInTheDocument();
    expect(screen.getByText("Active pipeline jobs")).toBeInTheDocument();
  });

  it("makes 4 useQuery calls", () => {
    render(<Component />);
    expect(mockUseQuery).toHaveBeenCalledTimes(4);
  });

  it("passes matterId-based query keys", () => {
    render(<Component />);
    const queryKeys = mockUseQuery.mock.calls.map(
      (call: [{ queryKey: string[] }]) => call[0].queryKey[0],
    );
    expect(queryKeys).toContain("doc-count");
    expect(queryKeys).toContain("graph-stats-summary");
    expect(queryKeys).toContain("active-jobs");
    expect(queryKeys).toContain("hot-doc-count");
  });
});
