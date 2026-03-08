import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(() => ({ data: null, isLoading: false, error: null })),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth-store";
import { PathFinder } from "@/components/entities/path-finder";
import { CypherExplorer } from "@/components/entities/cypher-explorer";
import { ReportingChain } from "@/components/entities/reporting-chain";

const mockUseQuery = vi.mocked(useQuery);

describe("PathFinder", () => {
  beforeEach(() => {
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
  });

  it("renders with source and target inputs", () => {
    render(<PathFinder />);
    expect(screen.getByText("Path Finder")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. John Smith")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Acme Corp")).toBeInTheDocument();
  });

  it("disables Find Path button when inputs are empty", () => {
    render(<PathFinder />);
    const btn = screen.getByRole("button", { name: /find path/i });
    expect(btn).toBeDisabled();
  });

  it("enables Find Path button when both inputs have values", () => {
    render(<PathFinder />);
    fireEvent.change(screen.getByPlaceholderText("e.g. John Smith"), {
      target: { value: "Alice" },
    });
    fireEvent.change(screen.getByPlaceholderText("e.g. Acme Corp"), {
      target: { value: "Bob" },
    });
    const btn = screen.getByRole("button", { name: /find path/i });
    expect(btn).toBeEnabled();
  });

  it("collapses and expands on header click", () => {
    render(<PathFinder />);
    // Content is visible initially
    expect(screen.getByPlaceholderText("e.g. John Smith")).toBeInTheDocument();

    // Click header to collapse
    fireEvent.click(screen.getByText("Path Finder"));
    expect(screen.queryByPlaceholderText("e.g. John Smith")).not.toBeInTheDocument();

    // Click header to expand
    fireEvent.click(screen.getByText("Path Finder"));
    expect(screen.getByPlaceholderText("e.g. John Smith")).toBeInTheDocument();
  });

  it("shows no path message when results are empty", () => {
    mockUseQuery.mockReturnValue({
      data: { entity_a: "Alice", entity_b: "Bob", paths: [] },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<PathFinder />);
    expect(screen.getByText(/no path found/i)).toBeInTheDocument();
  });

  it("displays path results with nodes and edges", () => {
    mockUseQuery.mockReturnValue({
      data: {
        entity_a: "Alice",
        entity_b: "Bob",
        paths: [
          {
            nodes: ["Alice", "Acme", "Bob"],
            relationships: ["WORKS_AT", "WORKS_AT"],
            hops: 2,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<PathFinder />);
    expect(screen.getByText("Found 1 path(s)")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getAllByText("WORKS_AT")).toHaveLength(2);
  });
});

describe("CypherExplorer", () => {
  beforeEach(() => {
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
  });

  it("renders nothing for non-admin users", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "user@test.com",
      full_name: "Test User",
      role: "reviewer",
      is_active: true,
      created_at: "2024-01-01",
    });
    const { container } = render(<CypherExplorer />);
    expect(container.innerHTML).toBe("");
  });

  it("renders for admin users", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "admin@test.com",
      full_name: "Admin User",
      role: "admin",
      is_active: true,
      created_at: "2024-01-01",
    });
    render(<CypherExplorer />);
    expect(screen.getByText(/advanced query/i)).toBeInTheDocument();
  });

  it("renders for attorney users", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "atty@test.com",
      full_name: "Attorney",
      role: "attorney",
      is_active: true,
      created_at: "2024-01-01",
    });
    render(<CypherExplorer />);
    expect(screen.getByText(/advanced query/i)).toBeInTheDocument();
  });

  it("starts collapsed and expands on click", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "admin@test.com",
      full_name: "Admin",
      role: "admin",
      is_active: true,
      created_at: "2024-01-01",
    });
    render(<CypherExplorer />);

    // Starts collapsed - no textarea visible
    expect(screen.queryByLabelText("Cypher query")).not.toBeInTheDocument();

    // Expand
    fireEvent.click(screen.getByText(/advanced query/i));
    expect(screen.getByLabelText("Cypher query")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run/i })).toBeInTheDocument();
  });

  it("disables Run button when query is empty", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "admin@test.com",
      full_name: "Admin",
      role: "admin",
      is_active: true,
      created_at: "2024-01-01",
    });
    render(<CypherExplorer />);
    fireEvent.click(screen.getByText(/advanced query/i));
    expect(screen.getByRole("button", { name: /run/i })).toBeDisabled();
  });

  it("shows results in a table", () => {
    useAuthStore.getState().login("token", "refresh", {
      id: "1",
      email: "admin@test.com",
      full_name: "Admin",
      role: "admin",
      is_active: true,
      created_at: "2024-01-01",
    });
    mockUseQuery.mockReturnValue({
      data: {
        results: [
          { name: "Alice", type: "PERSON" },
          { name: "Bob", type: "PERSON" },
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<CypherExplorer />);
    fireEvent.click(screen.getByText(/advanced query/i));
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("type")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });
});

describe("ReportingChain", () => {
  beforeEach(() => {
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
  });

  it("shows loading skeleton", () => {
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<ReportingChain personName="John Doe" />);
    expect(screen.getByText("Reporting Chain")).toBeInTheDocument();
  });

  it("shows no chain message when empty", () => {
    mockUseQuery.mockReturnValue({
      data: { person: "John Doe", chains: [] },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<ReportingChain personName="John Doe" />);
    expect(screen.getByText(/no reporting chain found/i)).toBeInTheDocument();
  });

  it("renders chain nodes with indentation", () => {
    mockUseQuery.mockReturnValue({
      data: {
        person: "John Doe",
        chains: [
          [
            { name: "CEO", title: "Chief Executive" },
            { name: "VP", title: "Vice President" },
            { name: "John Doe", title: "Manager" },
          ],
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    render(<ReportingChain personName="John Doe" />);
    expect(screen.getByText("CEO")).toBeInTheDocument();
    expect(screen.getByText("VP")).toBeInTheDocument();
    expect(screen.getByText("John Doe")).toBeInTheDocument();
    expect(screen.getByText("(Chief Executive)")).toBeInTheDocument();
  });

  it("shows error message on failure", () => {
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as unknown as ReturnType<typeof useQuery>);
    render(<ReportingChain personName="John Doe" />);
    expect(screen.getByText(/failed to load reporting chain/i)).toBeInTheDocument();
  });
});
