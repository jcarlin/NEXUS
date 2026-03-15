import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockNavigate = vi.fn();
const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  useNavigate: () => mockNavigate,
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
      selector({ matterId: "matter-1", datasetId: null }),
    {
      getState: () => ({ matterId: "matter-1", datasetId: null }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));

vi.mock("@/components/documents/document-table", () => ({
  DocumentTable: ({ data, loading }: { data: unknown[]; loading?: boolean }) => (
    <div data-testid="document-table" data-loading={loading}>
      {data.length} documents
    </div>
  ),
}));

vi.mock("@/components/documents/document-filters", () => ({
  DocumentFilters: ({
    search,
    onSearchChange,
  }: {
    search: string;
    onSearchChange: (v: string) => void;
  }) => (
    <input
      data-testid="search-input"
      value={search}
      onChange={(e) => onSearchChange(e.target.value)}
    />
  ),
}));

vi.mock("@/components/ui/pagination", () => ({
  Pagination: ({ total }: { total: number }) => (
    <div data-testid="pagination">Total: {total}</div>
  ),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

import { Route } from "@/routes/documents/index.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("DocumentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Documents heading", () => {
    render(<Component />);
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("shows Loading... when no data yet", () => {
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows document count when data is loaded", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "documents") {
        return { data: { items: [], total: 42, offset: 0, limit: 50 }, isLoading: false };
      }
      return { data: undefined, isLoading: false };
    });

    render(<Component />);
    expect(screen.getByText("42 documents")).toBeInTheDocument();
  });

  it("renders Import button", () => {
    render(<Component />);
    expect(screen.getByText("Import")).toBeInTheDocument();
  });

  it("navigates to import on button click", () => {
    render(<Component />);
    fireEvent.click(screen.getByText("Import"));
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/documents/import" });
  });

  it("renders DocumentTable component", () => {
    render(<Component />);
    expect(screen.getByTestId("document-table")).toBeInTheDocument();
  });

  it("renders search filters", () => {
    render(<Component />);
    expect(screen.getByTestId("search-input")).toBeInTheDocument();
  });

  it("shows pagination when data is available", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "documents") {
        return { data: { items: [], total: 100, offset: 0, limit: 50 }, isLoading: false };
      }
      return { data: undefined, isLoading: false };
    });

    render(<Component />);
    expect(screen.getByTestId("pagination")).toBeInTheDocument();
  });
});
