import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();
const mockInvalidateQueries = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/hooks/use-notifications", () => ({
  useNotifications: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

import { Route } from "@/routes/admin/pages.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

const SAMPLE_FLAGS = {
  items: [
    {
      flag_name: "enable_page_chat",
      display_name: "Chat",
      description: "Show the Chat page in the sidebar navigation.",
      category: "pages",
      risk_level: "safe",
      enabled: false,
      is_override: true,
      env_default: true,
      depends_on: [],
      updated_at: null,
      updated_by: null,
    },
    {
      flag_name: "enable_page_comms_matrix",
      display_name: "Comms Matrix",
      description: "Show the Comms Matrix page in the sidebar navigation.",
      category: "pages",
      risk_level: "safe",
      enabled: true,
      is_override: false,
      env_default: true,
      depends_on: [],
      updated_at: null,
      updated_by: null,
    },
    {
      flag_name: "enable_page_hot_docs",
      display_name: "Hot Docs",
      description: "Show the Hot Docs page in the sidebar navigation.",
      category: "pages",
      risk_level: "safe",
      enabled: true,
      is_override: false,
      env_default: true,
      depends_on: [],
      updated_at: null,
      updated_by: null,
    },
    // Non-page flag — should be filtered out
    {
      flag_name: "enable_reranker",
      display_name: "Reranker",
      description: "Cross-encoder reranker",
      category: "retrieval",
      risk_level: "cache_clear",
      enabled: true,
      is_override: false,
      env_default: false,
      depends_on: [],
      updated_at: null,
      updated_by: null,
    },
  ],
};

describe("PagesPage", () => {
  let mutateFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mutateFn = vi.fn();
    mockUseMutation.mockReturnValue({ mutate: mutateFn, isPending: false });
  });

  it("renders heading", () => {
    mockUseQuery.mockReturnValue({ data: SAMPLE_FLAGS, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Pages")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders only page flags grouped by section", () => {
    mockUseQuery.mockReturnValue({ data: SAMPLE_FLAGS, isLoading: false });
    render(<Component />);
    // Page flags should be visible
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Comms Matrix")).toBeInTheDocument();
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
    // Non-page flag should NOT be visible
    expect(screen.queryByText("Reranker")).not.toBeInTheDocument();
    // Section headers
    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.getByText("Analysis")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("calls mutation on toggle", async () => {
    mockUseQuery.mockReturnValue({ data: SAMPLE_FLAGS, isLoading: false });
    render(<Component />);

    const switches = screen.getAllByRole("switch");
    await userEvent.click(switches[0]);

    expect(mutateFn).toHaveBeenCalledWith({
      flagName: "enable_page_chat",
      enabled: true,
    });
  });
});
