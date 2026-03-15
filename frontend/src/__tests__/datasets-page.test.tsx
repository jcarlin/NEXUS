import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
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

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ user: { role: "admin" } }),
    {
      getState: () => ({ user: { role: "admin" } }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/lib/dataset-dnd", () => ({
  buildDragPayload: vi.fn(),
  toggleSelection: vi.fn(),
  isAllSelected: () => false,
}));

vi.mock("@/lib/dataset-access", () => ({
  canManageDatasetAccess: () => true,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

vi.mock("@/components/datasets/dataset-access-dialog", () => ({
  DatasetAccessDialog: () => null,
}));

vi.mock("@/components/datasets/ingest-dialog", () => ({
  IngestDialog: () => null,
}));

vi.mock("@/components/datasets/ingest-progress", () => ({
  IngestProgress: () => null,
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { Route } from "@/routes/datasets/index.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("DatasetsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
  });

  it("renders Datasets heading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Datasets")).toBeInTheDocument();
  });

  it("shows 'Select a dataset from the sidebar' when no dataset selected", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Select a dataset from the sidebar")).toBeInTheDocument();
  });

  it("shows loading text when tree is loading", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "datasets" && opts.queryKey[1] === "tree") {
        return { data: undefined, isLoading: true };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows 'No datasets yet' when tree is empty", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "datasets" && opts.queryKey[1] === "tree") {
        return {
          data: { roots: [], total_datasets: 0 },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("No datasets yet. Create one to get started.")).toBeInTheDocument();
  });

  it("renders dataset tree items", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "datasets" && opts.queryKey[1] === "tree") {
        return {
          data: {
            roots: [
              {
                id: "ds-1",
                name: "Contracts",
                description: "",
                document_count: 25,
                children: [],
              },
              {
                id: "ds-2",
                name: "Emails",
                description: "",
                document_count: 50,
                children: [],
              },
            ],
            total_datasets: 2,
          },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("Contracts")).toBeInTheDocument();
    expect(screen.getByText("Emails")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });
});
