import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

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

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/entities/entity-table", () => ({
  EntityTable: ({ data, loading }: { data: unknown[]; loading?: boolean }) => (
    <div data-testid="entity-table" data-loading={loading}>
      {data.length} entities
    </div>
  ),
}));

vi.mock("@/components/ui/pagination", () => ({
  Pagination: ({ total }: { total: number }) => (
    <div data-testid="pagination">Total: {total}</div>
  ),
}));

import { Route } from "@/routes/entities/index";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("EntitiesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Entities heading", () => {
    render(<Component />);
    expect(screen.getByText("Entities")).toBeInTheDocument();
  });

  it("shows Loading... when no data", () => {
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows entity count when data loaded", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 135, offset: 0, limit: 50 },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("135 entities")).toBeInTheDocument();
  });

  it("renders Network Graph link", () => {
    render(<Component />);
    const link = screen.getByText("Network Graph").closest("a");
    expect(link).toHaveAttribute("href", "/entities/network");
  });

  it("renders entity table", () => {
    render(<Component />);
    expect(screen.getByTestId("entity-table")).toBeInTheDocument();
  });

  it("renders search input", () => {
    render(<Component />);
    expect(screen.getByPlaceholderText("Search entities...")).toBeInTheDocument();
  });

  it("shows pagination when data available", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 200, offset: 0, limit: 50 },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByTestId("pagination")).toBeInTheDocument();
  });
});
