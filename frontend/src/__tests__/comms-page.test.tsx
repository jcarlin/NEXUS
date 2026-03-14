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

vi.mock("@/components/analytics/comm-matrix", () => ({
  CommMatrix: ({
    matrix,
    loading,
  }: {
    matrix: unknown[];
    loading?: boolean;
  }) => (
    <div data-testid="comm-matrix" data-loading={loading}>
      {matrix.length} pairs
    </div>
  ),
}));

vi.mock("@/components/analytics/comm-drilldown", () => ({
  CommDrilldown: () => <div data-testid="comm-drilldown">Drilldown</div>,
}));

import { Route } from "@/routes/analytics/comms.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("CommsMatrixPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Communication Analysis heading", () => {
    render(<Component />);
    expect(screen.getByText("Communication Analysis")).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<Component />);
    expect(
      screen.getByText("Visualize communication patterns between entities and explore email threads."),
    ).toBeInTheDocument();
  });

  it("renders Matrix tab", () => {
    render(<Component />);
    expect(screen.getByText("Matrix")).toBeInTheDocument();
  });

  it("renders Email Threads tab", () => {
    render(<Component />);
    expect(screen.getByText("Email Threads")).toBeInTheDocument();
  });

  it("renders comm matrix component", () => {
    render(<Component />);
    expect(screen.getByTestId("comm-matrix")).toBeInTheDocument();
  });

  it("shows matrix data when loaded", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "communication-matrix") {
        return {
          data: {
            pairs: [
              {
                sender_name: "Alice",
                sender_email: "alice@test.com",
                recipient_name: "Bob",
                recipient_email: "bob@test.com",
                relationship_type: "email",
                message_count: 10,
                earliest: "2024-01-01",
                latest: "2024-03-01",
              },
            ],
          },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByTestId("comm-matrix")).toHaveTextContent("1 pairs");
  });
});
