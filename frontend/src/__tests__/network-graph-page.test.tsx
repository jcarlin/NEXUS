import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  QueryClient: vi.fn(),
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (s: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "admin" } }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/components/entities/network-graph", () => ({
  NetworkGraph: React.forwardRef(
    (
      { entities }: { entities: unknown[] },
      _ref: React.Ref<unknown>,
    ) => <div data-testid="network-graph">{entities.length} nodes</div>,
  ),
}));

vi.mock("@/components/entities/graph-controls", () => ({
  GraphControls: ({ activeTypes }: { activeTypes: Set<string> }) => (
    <div data-testid="graph-controls">{activeTypes.size} types</div>
  ),
}));

vi.mock("@/components/entities/path-finder", () => ({
  PathFinder: () => <div data-testid="path-finder">Path Finder</div>,
}));

vi.mock("@/components/entities/cypher-explorer", () => ({
  CypherExplorer: () => <div data-testid="cypher-explorer">Cypher Explorer</div>,
}));

import { Route } from "@/routes/entities/network.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("NetworkGraphPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Network Graph heading", () => {
    render(<Component />);
    expect(screen.getByText("Network Graph")).toBeInTheDocument();
  });

  it("renders Back link", () => {
    render(<Component />);
    expect(screen.getByText("Back")).toBeInTheDocument();
  });

  it("shows Loading... text when data not loaded", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows entity and connection counts when loaded", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "entities-network") {
        return {
          data: { items: [{ id: "e1" }, { id: "e2" }], total: 2 },
          isLoading: false,
        };
      }
      if (key === "entities-network-connections") {
        return { data: [{ source: "e1", target: "e2" }], isLoading: false };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("2 entities, 1 connections")).toBeInTheDocument();
  });

  it("renders graph controls", () => {
    render(<Component />);
    expect(screen.getByTestId("graph-controls")).toBeInTheDocument();
  });

  it("renders path finder", () => {
    render(<Component />);
    expect(screen.getByTestId("path-finder")).toBeInTheDocument();
  });

  it("renders cypher explorer", () => {
    render(<Component />);
    expect(screen.getByTestId("cypher-explorer")).toBeInTheDocument();
  });
});
