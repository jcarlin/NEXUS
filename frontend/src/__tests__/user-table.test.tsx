import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { UserTable } from "@/components/admin/user-table";
import type { User } from "@/types";

vi.mock("@/components/ui/data-table-column-header", () => ({
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

vi.mock("@/components/ui/data-table-toolbar", () => ({
  DataTableToolbar: ({ searchPlaceholder }: { searchPlaceholder: string }) => (
    <input placeholder={searchPlaceholder} data-testid="toolbar-search" />
  ),
}));

const MOCK_USERS: User[] = [
  {
    id: "u1",
    email: "admin@nexus.com",
    full_name: "Admin User",
    role: "admin",
    is_active: true,
    created_at: "2024-01-15T10:00:00Z",
  } as User,
  {
    id: "u2",
    email: "attorney@nexus.com",
    full_name: "Jane Attorney",
    role: "attorney",
    is_active: true,
    created_at: "2024-02-01T09:00:00Z",
  } as User,
  {
    id: "u3",
    email: "reviewer@nexus.com",
    full_name: "Bob Reviewer",
    role: "reviewer",
    is_active: false,
    created_at: "2024-03-01T08:00:00Z",
  } as User,
];

describe("UserTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders column headers", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Full Name")).toBeInTheDocument();
    expect(screen.getByText("Role")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
  });

  it("renders user emails", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    expect(screen.getByText("admin@nexus.com")).toBeInTheDocument();
    expect(screen.getByText("attorney@nexus.com")).toBeInTheDocument();
    expect(screen.getByText("reviewer@nexus.com")).toBeInTheDocument();
  });

  it("renders role badges", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("attorney")).toBeInTheDocument();
    expect(screen.getByText("reviewer")).toBeInTheDocument();
  });

  it("renders active/inactive status", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    const activeBadges = screen.getAllByText("Active");
    const inactiveBadge = screen.getByText("Inactive");
    expect(activeBadges.length).toBe(2);
    expect(inactiveBadge).toBeInTheDocument();
  });

  it("shows loading skeletons when isLoading=true", () => {
    const { container } = render(<UserTable data={[]} isLoading={true} />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows 'No users found.' for empty data", () => {
    render(<UserTable data={[]} isLoading={false} />);
    expect(screen.getByText("No users found.")).toBeInTheDocument();
  });

  it("renders search toolbar", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    expect(screen.getByPlaceholderText("Search users...")).toBeInTheDocument();
  });

  it("renders correct number of rows", () => {
    render(<UserTable data={MOCK_USERS} isLoading={false} />);
    const rows = screen.getAllByRole("row");
    // 1 header + 3 data rows
    expect(rows).toHaveLength(4);
  });
});
