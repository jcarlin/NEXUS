import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/components/ui/data-table-column-header", () => ({
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

vi.mock("@/components/ui/data-table-toolbar", () => ({
  DataTableToolbar: ({ searchPlaceholder }: { searchPlaceholder: string }) => (
    <input placeholder={searchPlaceholder} data-testid="toolbar-search" />
  ),
}));

vi.mock("@/components/ui/pagination", () => ({
  Pagination: ({ total }: { total: number }) => (
    <div data-testid="pagination">Total: {total}</div>
  ),
}));

vi.mock("@/components/exports/production-set-detail", () => ({
  ProductionSetDetail: () => <div data-testid="ps-detail">Detail</div>,
}));

import { ProductionSetList } from "@/components/exports/production-set-list";

const MOCK_SETS = [
  {
    id: "ps-1",
    name: "Production Set 1",
    description: "First set",
    document_count: 50,
    bates_prefix: "NEXUS",
    status: "draft",
    created_at: "2024-03-01T10:00:00Z",
    updated_at: "2024-03-01T10:00:00Z",
    matter_id: "m-1",
    bates_start: null,
    bates_end: null,
  },
  {
    id: "ps-2",
    name: "Production Set 2",
    description: "",
    document_count: 100,
    bates_prefix: "DOC",
    status: "exported",
    created_at: "2024-02-15T10:00:00Z",
    updated_at: "2024-02-15T10:00:00Z",
    matter_id: "m-1",
    bates_start: 1,
    bates_end: 100,
  },
];

describe("ProductionSetList", () => {
  const defaultProps = {
    data: MOCK_SETS,
    loading: false,
    total: 2,
    offset: 0,
    limit: 50,
    onOffsetChange: vi.fn(),
    onRefresh: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders column headers", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Documents")).toBeInTheDocument();
    expect(screen.getByText("Bates Prefix")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
  });

  it("renders production set names", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(screen.getByText("Production Set 1")).toBeInTheDocument();
    expect(screen.getByText("Production Set 2")).toBeInTheDocument();
  });

  it("renders status badges", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.getByText("exported")).toBeInTheDocument();
  });

  it("renders Bates prefix", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(screen.getByText("NEXUS")).toBeInTheDocument();
    expect(screen.getByText("DOC")).toBeInTheDocument();
  });

  it("shows Assign Bates button for draft sets", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(screen.getByText("Assign Bates")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    const { container } = render(
      <ProductionSetList {...defaultProps} data={[]} loading={true} />,
    );
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows empty message when no data", () => {
    render(
      <ProductionSetList {...defaultProps} data={[]} loading={false} />,
    );
    expect(
      screen.getByText("No production sets yet. Create one to get started."),
    ).toBeInTheDocument();
  });

  it("renders search toolbar", () => {
    render(<ProductionSetList {...defaultProps} />);
    expect(
      screen.getByPlaceholderText("Search production sets..."),
    ).toBeInTheDocument();
  });
});
