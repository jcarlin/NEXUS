import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
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

vi.mock("@/components/review/result-set-table", () => ({
  ResultSetTable: ({ data, loading }: { data: unknown[]; loading?: boolean }) => (
    <div data-testid="result-set-table" data-loading={loading}>
      {data.length} results
    </div>
  ),
}));

vi.mock("@/components/ui/pagination", () => ({
  Pagination: ({ total }: { total: number }) => (
    <div data-testid="pagination">Total: {total}</div>
  ),
}));

import { Route } from "@/routes/review/result-set.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("ResultSetPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Result Set heading", () => {
    render(<Component />);
    expect(screen.getByText("Result Set")).toBeInTheDocument();
  });

  it("shows Loading... when no data", () => {
    render(<Component />);
    expect(screen.getByText(/Loading\.\.\./)).toBeInTheDocument();
  });

  it("shows document count when data loaded", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "result-set") {
        return { data: { items: [], total: 25, offset: 0, limit: 50 }, isLoading: false };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText(/25 documents/)).toBeInTheDocument();
  });

  it("renders result set table", () => {
    render(<Component />);
    expect(screen.getByTestId("result-set-table")).toBeInTheDocument();
  });

  it("renders Duplicate Clusters section", () => {
    render(<Component />);
    expect(screen.getByText("Duplicate Clusters")).toBeInTheDocument();
  });
});
