import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/admin/user-table", () => ({
  UserTable: ({ data, isLoading }: { data: unknown[]; isLoading: boolean }) => (
    <div data-testid="user-table" data-loading={isLoading}>
      {data.length} users
    </div>
  ),
}));

vi.mock("@/components/admin/user-create-dialog", () => ({
  UserCreateDialog: ({ open }: { open: boolean }) => (
    open ? <div data-testid="create-dialog">Create User Dialog</div> : null
  ),
}));

import { Route } from "@/routes/admin/users";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("UsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders User Management heading", () => {
    render(<Component />);
    expect(screen.getByText("User Management")).toBeInTheDocument();
  });

  it("renders description", () => {
    render(<Component />);
    expect(screen.getByText("Manage platform users and roles.")).toBeInTheDocument();
  });

  it("renders Create User button", () => {
    render(<Component />);
    expect(screen.getByText("Create User")).toBeInTheDocument();
  });

  it("opens create dialog on button click", () => {
    render(<Component />);
    expect(screen.queryByTestId("create-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Create User"));
    expect(screen.getByTestId("create-dialog")).toBeInTheDocument();
  });

  it("renders user table", () => {
    render(<Component />);
    expect(screen.getByTestId("user-table")).toBeInTheDocument();
  });

  it("passes data to user table when loaded", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          { id: "u1", email: "admin@test.com", full_name: "Admin", role: "admin", is_active: true, created_at: "2024-01-01" },
        ],
        total: 1,
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByTestId("user-table")).toHaveTextContent("1 users");
  });
});
