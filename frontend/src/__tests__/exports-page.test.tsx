import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
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

vi.mock("@/components/exports/production-set-list", () => ({
  ProductionSetList: ({ data, loading }: { data: unknown[]; loading: boolean }) => (
    <div data-testid="production-set-list" data-loading={loading}>
      {data.length} sets
    </div>
  ),
}));

vi.mock("@/components/exports/export-job-list", () => ({
  ExportJobList: ({ data, loading }: { data: unknown[]; loading: boolean }) => (
    <div data-testid="export-job-list" data-loading={loading}>
      {data.length} jobs
    </div>
  ),
}));

vi.mock("@/components/exports/create-production-set-dialog", () => ({
  CreateProductionSetDialog: () => <button data-testid="create-ps-btn">New Production Set</button>,
}));

vi.mock("@/components/exports/create-export-dialog", () => ({
  CreateExportDialog: () => <button data-testid="create-export-btn">New Export</button>,
}));

import { Route } from "@/routes/review/exports";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("ExportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, refetch: vi.fn() });
  });

  it("renders Exports heading", () => {
    render(<Component />);
    expect(screen.getByText("Exports")).toBeInTheDocument();
  });

  it("renders description", () => {
    render(<Component />);
    expect(screen.getByText("Manage production sets and export jobs.")).toBeInTheDocument();
  });

  it("renders Production Sets tab", () => {
    render(<Component />);
    expect(screen.getByText(/Production Sets/)).toBeInTheDocument();
  });

  it("renders Export Jobs tab", () => {
    render(<Component />);
    expect(screen.getByText(/Export Jobs/)).toBeInTheDocument();
  });

  it("shows counts in tab labels when data loaded", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "production-sets") {
        return { data: { items: [], total: 5 }, isLoading: false, refetch: vi.fn() };
      }
      if (key === "export-jobs") {
        return { data: { items: [], total: 3 }, isLoading: false, refetch: vi.fn() };
      }
      return { data: undefined, isLoading: false, refetch: vi.fn() };
    });
    render(<Component />);
    expect(screen.getByText("Production Sets (5)")).toBeInTheDocument();
    expect(screen.getByText("Export Jobs (3)")).toBeInTheDocument();
  });

  it("renders production set list", () => {
    render(<Component />);
    expect(screen.getByTestId("production-set-list")).toBeInTheDocument();
  });

  it("renders create buttons", () => {
    render(<Component />);
    expect(screen.getByTestId("create-ps-btn")).toBeInTheDocument();
    expect(screen.getByTestId("create-export-btn")).toBeInTheDocument();
  });
});
