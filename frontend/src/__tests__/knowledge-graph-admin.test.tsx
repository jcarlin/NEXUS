import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ---- Mocks ---- //

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({ accessToken: "test-token" }),
  },
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

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => () => ({ component: () => null }),
  Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
    <a href={props.to}>{children}</a>
  ),
}));

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();
const mockUseQueryClient = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQueryClient: () => mockUseQueryClient(),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockUseQueryClient.mockReturnValue({ invalidateQueries: vi.fn() });
  mockUseMutation.mockReturnValue({ isPending: false, mutate: vi.fn() });
});

// ---- Helper to render the page component ---- //

async function renderPage() {
  const mod = await import("@/routes/admin/knowledge-graph");
  // The component is the default export from createFileRoute; we need to get
  // the actual component function. Since we mock createFileRoute, we access it
  // via the module's Route.
  // Actually the component is KnowledgeGraphPage which is defined in the module.
  // With our mock of createFileRoute, Route won't give us the component directly.
  // Instead, re-export test: the module defines function KnowledgeGraphPage and
  // passes it to createFileRoute(...).component(). Our mock returns a no-op.
  // We need to render the component directly. Let's access it differently.

  // The file structure is:
  //   export const Route = createFileRoute(...)({ component: KnowledgeGraphPage });
  //   function KnowledgeGraphPage() { ... }
  // With our mock, createFileRoute returns () => () => ({ component: () => null })
  // So Route = { component: () => null } and the actual component is not exported.
  // We need a different approach: render via the module's internal component.

  // Let's just check that the module exports Route successfully.
  expect(mod.Route).toBeDefined();
  return mod;
}

// ---- Tests ---- //

describe("Knowledge Graph Admin Page", () => {
  it("module exports Route", async () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    const mod = await renderPage();
    expect(mod.Route).toBeDefined();
  });

  it("renders graph health stats when data is loaded", async () => {
    const mockData = {
      total_nodes: 1234,
      total_edges: 5678,
      node_counts: { PERSON: 100, ORGANIZATION: 50 },
      edge_counts: { RELATED_TO: 200 },
      documents: [
        {
          doc_id: "doc-1",
          filename: "contract.pdf",
          entity_count: 15,
          neo4j_indexed: true,
          created_at: "2024-06-01T00:00:00Z",
        },
        {
          doc_id: "doc-2",
          filename: "memo.pdf",
          entity_count: 3,
          neo4j_indexed: false,
          created_at: "2024-06-02T00:00:00Z",
        },
      ],
      total_documents: 10,
      indexed_documents: 7,
    };

    mockUseQuery.mockReturnValue({ data: mockData, isLoading: false });

    // We need to re-mock createFileRoute to capture the component
    let CapturedComponent: React.ComponentType | null = null;
    vi.doMock("@tanstack/react-router", () => ({
      createFileRoute: () => (opts: { component: React.ComponentType }) => {
        CapturedComponent = opts.component;
        return opts;
      },
      Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
        <a href={props.to}>{children}</a>
      ),
    }));

    // Re-import to get fresh module with new mock
    vi.resetModules();
    // Re-apply all mocks after resetModules
    vi.doMock("@/stores/auth-store", () => ({
      useAuthStore: { getState: () => ({ accessToken: "test-token" }) },
    }));
    vi.doMock("@/stores/app-store", () => ({
      useAppStore: Object.assign(
        (selector: (s: Record<string, unknown>) => unknown) =>
          selector({ matterId: "matter-1" }),
        { getState: () => ({ matterId: "matter-1" }) },
      ),
    }));
    vi.doMock("sonner", () => ({
      toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
    }));
    vi.doMock("@tanstack/react-query", () => ({
      useQuery: () => ({ data: mockData, isLoading: false }),
      useMutation: () => ({ isPending: false, mutate: vi.fn() }),
      useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    }));
    vi.doMock("@/api/client", () => ({ apiClient: vi.fn() }));

    await import("@/routes/admin/knowledge-graph");

    expect(CapturedComponent).not.toBeNull();
    const Component = CapturedComponent as unknown as React.ComponentType;
    render(<Component />);

    // Verify stats
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("5,678")).toBeInTheDocument();
    expect(screen.getByText("Total Nodes")).toBeInTheDocument();
    expect(screen.getByText("Total Edges")).toBeInTheDocument();
    expect(screen.getByText("7/10")).toBeInTheDocument();

    // Verify node type badges
    expect(screen.getByText("PERSON: 100")).toBeInTheDocument();
    expect(screen.getByText("ORGANIZATION: 50")).toBeInTheDocument();

    // Verify document table
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("memo.pdf")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();

    // Verify action buttons
    expect(screen.getByText("Re-process All Unprocessed")).toBeInTheDocument();
    expect(screen.getByText("Resolve Entities")).toBeInTheDocument();
    expect(screen.getByText("Resolve (Agent)")).toBeInTheDocument();
  });

  it("shows loading state", async () => {
    let CapturedComponent: React.ComponentType | null = null;

    vi.resetModules();
    vi.doMock("@tanstack/react-router", () => ({
      createFileRoute: () => (opts: { component: React.ComponentType }) => {
        CapturedComponent = opts.component;
        return opts;
      },
      Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
        <a href={props.to}>{children}</a>
      ),
    }));
    vi.doMock("@/stores/auth-store", () => ({
      useAuthStore: { getState: () => ({ accessToken: "test-token" }) },
    }));
    vi.doMock("@/stores/app-store", () => ({
      useAppStore: Object.assign(
        (selector: (s: Record<string, unknown>) => unknown) =>
          selector({ matterId: "matter-1" }),
        { getState: () => ({ matterId: "matter-1" }) },
      ),
    }));
    vi.doMock("sonner", () => ({
      toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
    }));
    vi.doMock("@tanstack/react-query", () => ({
      useQuery: () => ({ data: undefined, isLoading: true }),
      useMutation: () => ({ isPending: false, mutate: vi.fn() }),
      useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    }));
    vi.doMock("@/api/client", () => ({ apiClient: vi.fn() }));

    await import("@/routes/admin/knowledge-graph");
    expect(CapturedComponent).not.toBeNull();
    const Component = CapturedComponent as unknown as React.ComponentType;
    render(<Component />);

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.getByText("Loading documents...")).toBeInTheDocument();
  });

  it("shows empty state when no documents", async () => {
    const emptyData = {
      total_nodes: 0,
      total_edges: 0,
      node_counts: {},
      edge_counts: {},
      documents: [],
      total_documents: 0,
      indexed_documents: 0,
    };

    let CapturedComponent: React.ComponentType | null = null;

    vi.resetModules();
    vi.doMock("@tanstack/react-router", () => ({
      createFileRoute: () => (opts: { component: React.ComponentType }) => {
        CapturedComponent = opts.component;
        return opts;
      },
      Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
        <a href={props.to}>{children}</a>
      ),
    }));
    vi.doMock("@/stores/auth-store", () => ({
      useAuthStore: { getState: () => ({ accessToken: "test-token" }) },
    }));
    vi.doMock("@/stores/app-store", () => ({
      useAppStore: Object.assign(
        (selector: (s: Record<string, unknown>) => unknown) =>
          selector({ matterId: "matter-1" }),
        { getState: () => ({ matterId: "matter-1" }) },
      ),
    }));
    vi.doMock("sonner", () => ({
      toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
    }));
    vi.doMock("@tanstack/react-query", () => ({
      useQuery: () => ({ data: emptyData, isLoading: false }),
      useMutation: () => ({ isPending: false, mutate: vi.fn() }),
      useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    }));
    vi.doMock("@/api/client", () => ({ apiClient: vi.fn() }));

    await import("@/routes/admin/knowledge-graph");
    expect(CapturedComponent).not.toBeNull();
    const Component = CapturedComponent as unknown as React.ComponentType;
    render(<Component />);

    expect(screen.getByText("Total Nodes")).toBeInTheDocument();
    expect(screen.getByText("Total Edges")).toBeInTheDocument();
    expect(screen.getByText("No documents found.")).toBeInTheDocument();
  });
});
