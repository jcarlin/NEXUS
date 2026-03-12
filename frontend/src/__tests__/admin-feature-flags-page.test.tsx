import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
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
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

import { Route } from "@/routes/admin/feature-flags";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("FeatureFlagsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
  });

  it("renders Feature Flags heading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Feature Flags")).toBeInTheDocument();
  });

  it("renders description text", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(
      screen.getByText(/Toggle feature flags at runtime/),
    ).toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    render(<Component />);
    expect(screen.getByText("Loading flags...")).toBeInTheDocument();
  });

  it("renders flags grouped by category", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          {
            flag_name: "enable_hybrid_search",
            display_name: "Hybrid Search",
            description: "Enable hybrid dense+sparse search",
            category: "retrieval",
            risk_level: "safe",
            enabled: true,
            is_override: false,
            env_default: true,
            updated_at: null,
            updated_by: null,
          },
          {
            flag_name: "enable_crag",
            display_name: "CRAG Grading",
            description: "Corrective RAG grading",
            category: "query",
            risk_level: "cache_clear",
            enabled: false,
            is_override: true,
            env_default: false,
            updated_at: "2024-01-01",
            updated_by: "admin",
          },
        ],
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("Retrieval & Embedding")).toBeInTheDocument();
    expect(screen.getByText("Query Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Hybrid Search")).toBeInTheDocument();
    expect(screen.getByText("CRAG Grading")).toBeInTheDocument();
  });

  it("shows risk level badges", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          {
            flag_name: "test_flag",
            display_name: "Test Flag",
            description: "Test desc",
            category: "retrieval",
            risk_level: "safe",
            enabled: true,
            is_override: false,
            env_default: true,
            updated_at: null,
            updated_by: null,
          },
        ],
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("Safe")).toBeInTheDocument();
  });

  it("shows DB Override badge for overridden flags", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          {
            flag_name: "test_flag",
            display_name: "Test Flag",
            description: "Test desc",
            category: "retrieval",
            risk_level: "safe",
            enabled: true,
            is_override: true,
            env_default: false,
            updated_at: null,
            updated_by: null,
          },
        ],
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("DB Override")).toBeInTheDocument();
  });

  it("shows Reset button for overridden flags", () => {
    mockUseQuery.mockReturnValue({
      data: {
        items: [
          {
            flag_name: "test_flag",
            display_name: "Test Flag",
            description: "Test desc",
            category: "retrieval",
            risk_level: "safe",
            enabled: true,
            is_override: true,
            env_default: false,
            updated_at: null,
            updated_by: null,
          },
        ],
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("Reset")).toBeInTheDocument();
  });
});
