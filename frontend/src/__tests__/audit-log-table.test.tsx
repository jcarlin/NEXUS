import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { AuditLogTable } from "@/components/admin/audit-log-table";
import type { AuditLogEntry } from "@/types";

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
  apiFetchRaw: vi.fn(),
}));

vi.mock("@/components/ui/data-table-column-header", () => ({
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

vi.mock("@/components/ui/data-table-toolbar", () => ({
  DataTableToolbar: ({
    searchPlaceholder,
    children,
  }: {
    searchPlaceholder: string;
    children?: React.ReactNode;
  }) => (
    <div data-testid="toolbar">
      <input placeholder={searchPlaceholder} />
      {children}
    </div>
  ),
}));

const MOCK_ENTRIES: AuditLogEntry[] = [
  {
    id: "1",
    user_email: "admin@test.com",
    action: "GET",
    resource: "/api/v1/documents",
    status_code: 200,
    ip_address: "127.0.0.1",
    duration_ms: 50,
    created_at: "2024-03-01T10:00:00Z",
  } as AuditLogEntry,
  {
    id: "2",
    user_email: "user@test.com",
    action: "POST",
    resource: "/api/v1/query",
    status_code: 400,
    ip_address: "192.168.1.1",
    duration_ms: 120,
    created_at: "2024-03-01T11:00:00Z",
  } as AuditLogEntry,
  {
    id: "3",
    user_email: null,
    action: "GET",
    resource: "/api/v1/health",
    status_code: 500,
    ip_address: "10.0.0.1",
    duration_ms: null,
    created_at: "2024-03-01T12:00:00Z",
  } as AuditLogEntry,
];

describe("AuditLogTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders column headers", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("Timestamp")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("Resource")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("IP")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
  });

  it("renders user emails", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("admin@test.com")).toBeInTheDocument();
    expect(screen.getByText("user@test.com")).toBeInTheDocument();
  });

  it("shows 'anonymous' for null user email", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });

  it("renders action badges", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    const getActions = screen.getAllByText("GET");
    expect(getActions.length).toBe(2);
    expect(screen.getByText("POST")).toBeInTheDocument();
  });

  it("renders status codes", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("400")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
  });

  it("renders Export button", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("Export")).toBeInTheDocument();
  });

  it("shows loading skeletons when isLoading=true", () => {
    const { container } = render(<AuditLogTable data={[]} isLoading={true} />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows 'No audit log entries found.' for empty data", () => {
    render(<AuditLogTable data={[]} isLoading={false} />);
    expect(screen.getByText("No audit log entries found.")).toBeInTheDocument();
  });

  it("shows entry count text", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByText("Showing 3 of 3 entries")).toBeInTheDocument();
  });

  it("renders search toolbar", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByPlaceholderText("Search audit logs...")).toBeInTheDocument();
  });
});
