import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1" }),
    {
      getState: () => ({ matterId: "matter-1" }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/hooks/use-feature-flags", () => ({
  useFeatureFlag: () => true,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/components/review/hot-doc-table", () => ({
  HotDocTable: ({ data, loading }: { data: unknown[]; loading?: boolean }) => (
    <div data-testid="hot-doc-table" data-loading={loading}>
      {data.length} hot docs
    </div>
  ),
}));

vi.mock("@/components/ui/feature-disabled-banner", () => ({
  FeatureDisabledBanner: ({ featureName }: { featureName: string }) => (
    <div data-testid="feature-disabled">{featureName}</div>
  ),
}));

import { Route } from "@/routes/review/hot-docs";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("HotDocsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders Hot Documents heading", () => {
    render(<Component />);
    expect(screen.getByText("Hot Documents")).toBeInTheDocument();
  });

  it("shows Loading... when no data", () => {
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows hot doc count when data loaded", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 7, offset: 0, limit: 50 },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("7 documents with hot score >= 0.7")).toBeInTheDocument();
  });

  it("renders hot doc table", () => {
    render(<Component />);
    expect(screen.getByTestId("hot-doc-table")).toBeInTheDocument();
  });

  it("does not show feature disabled banner when flag is enabled", () => {
    render(<Component />);
    expect(screen.queryByTestId("feature-disabled")).not.toBeInTheDocument();
  });
});
