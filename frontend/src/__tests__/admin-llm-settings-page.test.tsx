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

vi.mock("@/components/admin/llm-provider-dialog", () => ({
  LLMProviderDialog: () => null,
}));

vi.mock("@/components/admin/model-combobox", () => ({
  ModelCombobox: () => <input data-testid="model-combobox" />,
}));

import { Route } from "@/routes/admin/llm-settings";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("LLMSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMutation.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
    });
  });

  it("renders LLM Settings heading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("LLM Settings")).toBeInTheDocument();
  });

  it("renders description text", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(
      screen.getByText("Configure LLM providers, model assignments, and monitor usage costs."),
    ).toBeInTheDocument();
  });

  it("renders API Providers card", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("API Providers")).toBeInTheDocument();
  });

  it("renders Add Provider button", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("Add Provider")).toBeInTheDocument();
  });

  it("renders Tier Configuration card", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("Tier Configuration")).toBeInTheDocument();
  });

  it("shows 'No providers configured.' when empty", () => {
    mockUseQuery.mockReturnValue({
      data: { providers: [], tiers: [], env_defaults: {}, embedding: null },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<Component />);
    expect(screen.getByText("No providers configured.")).toBeInTheDocument();
  });

  it("renders provider table when providers exist", () => {
    mockUseQuery.mockReturnValue({
      data: {
        providers: [
          {
            id: "p1",
            provider: "anthropic",
            label: "Anthropic Cloud",
            api_key_set: true,
            base_url: "",
            is_active: true,
            created_at: "2024-01-01",
            updated_at: "2024-01-01",
          },
        ],
        tiers: [],
        env_defaults: {},
        embedding: null,
      },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<Component />);
    expect(screen.getByText("Anthropic Cloud")).toBeInTheDocument();
    expect(screen.getByText("anthropic")).toBeInTheDocument();
  });

  it("renders Ollama Models collapsible", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("Ollama Models")).toBeInTheDocument();
  });

  it("renders Cost Estimates collapsible", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, refetch: vi.fn() });
    render(<Component />);
    expect(screen.getByText("Cost Estimates")).toBeInTheDocument();
  });

  it("renders embedding info when available", () => {
    mockUseQuery.mockReturnValue({
      data: {
        providers: [],
        tiers: [],
        env_defaults: {},
        embedding: {
          provider: "local",
          model: "bge-small-en-v1.5",
          dimensions: 384,
        },
      },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<Component />);
    expect(screen.getByText("Embedding Model")).toBeInTheDocument();
    expect(screen.getByText("bge-small-en-v1.5")).toBeInTheDocument();
    expect(screen.getByText("384")).toBeInTheDocument();
  });
});
