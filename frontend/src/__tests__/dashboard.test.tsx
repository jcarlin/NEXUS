import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

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

vi.mock("@/components/dashboard/service-health", () => ({
  ServiceHealth: () => <div data-testid="service-health">Service Health</div>,
}));

// Track useQuery calls
const mockUseQuery = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

// Import after mocks so the route file picks up mocked dependencies
import { Route } from "@/routes/admin/dashboard.lazy";

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
          data: { total_nodes: 135, total_edges: 387, node_counts: { Entity: 98 } },
          isLoading: false,
        };
      }
      if (key === "active-jobs") {
        return { data: { items: [], total: 3 }, isLoading: false };
      }
      if (key === "hot-doc-count") {
        return { data: { items: [], total: 7 }, isLoading: false };
      }
      if (key === "corpus-stats") {
        return {
          data: { doc_count: 42, total_pages: 1250, total_size_bytes: 52428800 },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });

    render(<Component />);
    expect(screen.getByText("42")).toBeInTheDocument();
    // Entity count from node_counts.Entity appears in stat card and KG card
    expect(screen.getAllByText("98").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    // Corpus stats description: 50.0 MB · 1,250 pages
    expect(screen.getByText(/50\.0 MB/)).toBeInTheDocument();
    expect(screen.getByText(/1,250 pages/)).toBeInTheDocument();
  });

  it("renders sub-components for bottom section", () => {
    render(<Component />);
    expect(screen.getByTestId("recent-activity")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-status")).toBeInTheDocument();
    expect(screen.getByText("Entity Graph")).toBeInTheDocument();
  });

  it("shows descriptions for each stat card", () => {
    render(<Component />);
    expect(screen.getByText("Total ingested")).toBeInTheDocument();
    expect(screen.getByText("In knowledge graph")).toBeInTheDocument();
    expect(screen.getByText("Score >= 0.7")).toBeInTheDocument();
    expect(screen.getByText("Active pipeline jobs")).toBeInTheDocument();
  });

  it("makes 5 useQuery calls (doc-count, graph-stats, active-jobs, hot-docs, corpus-stats)", () => {
    render(<Component />);
    expect(mockUseQuery).toHaveBeenCalledTimes(5);
  });

  it("passes matterId-based query keys", () => {
    render(<Component />);
    const queryKeys = mockUseQuery.mock.calls.map(
      (call: { queryKey: string[] }[]) => call[0].queryKey[0],
    );
    expect(queryKeys).toContain("doc-count");
    expect(queryKeys).toContain("graph-stats-summary");
    expect(queryKeys).toContain("active-jobs");
    expect(queryKeys).toContain("hot-doc-count");
    expect(queryKeys).toContain("corpus-stats");
  });
});
