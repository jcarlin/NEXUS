import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/admin/audit-log-table", () => ({
  AuditLogTable: ({ data, isLoading }: { data: unknown[]; isLoading: boolean }) => (
    <div data-testid="audit-log-table" data-loading={isLoading}>
      {data.length} entries
    </div>
  ),
}));

import { Route } from "@/routes/admin/audit-log.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("AuditLogPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Audit Log heading", () => {
    render(<Component />);
    expect(screen.getByText("Audit Log")).toBeInTheDocument();
  });

  it("renders description", () => {
    render(<Component />);
    expect(
      screen.getByText("Review platform activity and API audit trail."),
    ).toBeInTheDocument();
  });

  it("renders audit log table", () => {
    render(<Component />);
    expect(screen.getByTestId("audit-log-table")).toBeInTheDocument();
  });

  it("passes loading state to table", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    render(<Component />);
    expect(screen.getByTestId("audit-log-table")).toHaveAttribute("data-loading", "true");
  });

  it("passes data to table when loaded", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          {
            id: "1",
            user_email: "admin@test.com",
            action: "GET",
            resource: "/api/v1/documents",
            status_code: 200,
            ip_address: "127.0.0.1",
            duration_ms: 50,
            created_at: "2024-03-01T10:00:00Z",
          },
        ],
        total: 1,
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByTestId("audit-log-table")).toHaveTextContent("1 entries");
  });
});
