import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();

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

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: (selector: (s: { matterId: string }) => unknown) =>
    selector({ matterId: "test-matter" }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

vi.mock("@/components/admin/operations/celery-panel", () => ({
  CeleryPanel: () => <div data-testid="celery-panel">CeleryPanel</div>,
}));

import { Route } from "@/routes/admin/pipeline.lazy";
import { BulkImportTable } from "@/components/admin/pipeline/bulk-import-table";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("PipelineMonitorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
  });

  it("renders Pipeline Monitor heading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Pipeline Monitor")).toBeInTheDocument();
  });

  it("renders description text", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(
      screen.getByText(/Real-time view of all ingestion jobs/),
    ).toBeInTheDocument();
  });

  it("renders all three tabs", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Bulk Imports")).toBeInTheDocument();
    expect(screen.getByText("Workers & Queues")).toBeInTheDocument();
  });

  it("shows Jobs tab by default with status filter", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 0, offset: 0, limit: 50 },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByPlaceholderText("Search by filename...")).toBeInTheDocument();
    expect(screen.getByText("No jobs found.")).toBeInTheDocument();
  });

  it("renders job rows when data is available", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "pipeline-jobs-table") {
        return {
          data: {
            items: [
              {
                job_id: "job-001",
                status: "processing",
                filename: "email_42.eml",
                document_type: "email",
                progress: { stage: "embedding", pages_parsed: 0, chunks_created: 0, entities_extracted: 0, embeddings_generated: 0 },
                created_at: "2026-03-20T10:00:00Z",
              },
              {
                job_id: "job-002",
                status: "failed",
                filename: "contract.pdf",
                document_type: "pdf",
                error: "Parse error",
                progress: null,
                created_at: "2026-03-20T09:00:00Z",
              },
            ],
            total: 2,
            offset: 0,
            limit: 50,
          },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("email_42.eml")).toBeInTheDocument();
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("shows summary stat cards", () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "pipeline-processing-count") {
        return { data: { total: 3 }, isLoading: false };
      }
      if (key === "pipeline-failed-count") {
        return { data: { total: 1 }, isLoading: false };
      }
      if (key === "pipeline-celery-summary" || key === "pipeline-queue-controls") {
        return {
          data: {
            workers: [{ hostname: "w1", status: "online" }],
            queues: [{ name: "default", reserved: 5, scheduled: 2, active: 1 }],
            active_tasks: [],
          },
          isLoading: false,
        };
      }
      if (key === "pipeline-imports-eta") {
        return { data: { items: [], total: 0 }, isLoading: false };
      }
      return { data: { items: [], total: 0, offset: 0, limit: 50 }, isLoading: false };
    });
    render(<Component />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Workers")).toBeInTheDocument();
    expect(screen.getByText("ETA")).toBeInTheDocument();
  });

  it("renders Bulk Imports tab trigger", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      isLoading: false,
    });
    render(<Component />);
    const tab = screen.getByRole("tab", { name: "Bulk Imports" });
    expect(tab).toBeInTheDocument();
  });

  it("renders Workers & Queues tab trigger", () => {
    mockUseQuery.mockReturnValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      isLoading: false,
    });
    render(<Component />);
    const tab = screen.getByRole("tab", { name: "Workers & Queues" });
    expect(tab).toBeInTheDocument();
  });

  it("shows skeleton loaders when loading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    render(<Component />);
    // Summary cards should show skeletons
    expect(screen.getByText("Pipeline Monitor")).toBeInTheDocument();
  });

  it("renders Live toggle in default-on state", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Live")).toBeInTheDocument();
    const switchEl = screen.getByRole("switch");
    expect(switchEl).toBeInTheDocument();
    expect(switchEl).toHaveAttribute("data-state", "checked");
  });

  it("toggles to Paused when clicked", async () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    const userEvent = (await import("@testing-library/user-event")).default;
    render(<Component />);
    const switchEl = screen.getByRole("switch");
    await userEvent.setup().click(switchEl);
    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(switchEl).toHaveAttribute("data-state", "unchecked");
  });

  it("shows pulsing green dot when live", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    // The pulsing dot has both bg-green-500 and animate-pulse classes
    const dot = document.querySelector(".bg-green-500.animate-pulse");
    expect(dot).toBeTruthy();
  });

  it("expands a bulk import row to show sub-table", () => {
    const bulkImportItem = {
      import_id: "imp-001",
      status: "complete",
      adapter_type: "local_folder",
      source_path: "/data/documents",
      total_documents: 10,
      processed_documents: 10,
      failed_documents: 0,
      skipped_documents: 0,
      elapsed_seconds: 120,
      estimated_remaining_seconds: null,
      error: null,
      created_at: "2026-03-20T10:00:00Z",
      updated_at: "2026-03-20T10:02:00Z",
    };
    const jobItem = {
      job_id: "job-100",
      status: "completed",
      stage: "done",
      filename: "report.pdf",
      progress: { chunks_created: 5 },
      error: null,
      created_at: "2026-03-20T10:00:00Z",
      updated_at: "2026-03-20T10:01:00Z",
    };
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "pipeline-bulk-imports") {
        return {
          data: { items: [bulkImportItem], total: 1, offset: 0, limit: 20 },
          isLoading: false,
        };
      }
      if (key === "bulk-import-jobs") {
        return {
          data: { items: [jobItem], total: 1, offset: 0, limit: 20 },
          isLoading: false,
        };
      }
      return { data: { items: [], total: 0, offset: 0, limit: 50 }, isLoading: false };
    });
    render(<BulkImportTable />);
    // Click the row to expand it
    const row = screen.getByText("local_folder").closest("tr");
    expect(row).toBeTruthy();
    fireEvent.click(row!);
    // Sub-table headers should appear
    expect(screen.getByText("Filename")).toBeInTheDocument();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("shows fallback text when expanded import has no linked jobs", () => {
    const bulkImportItem = {
      import_id: "imp-002",
      status: "complete",
      adapter_type: "google_drive",
      source_path: null,
      total_documents: 5,
      processed_documents: 5,
      failed_documents: 0,
      skipped_documents: 0,
      elapsed_seconds: 60,
      estimated_remaining_seconds: null,
      error: null,
      created_at: "2026-03-20T09:00:00Z",
      updated_at: "2026-03-20T09:01:00Z",
    };
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      const key = opts.queryKey[0];
      if (key === "pipeline-bulk-imports") {
        return {
          data: { items: [bulkImportItem], total: 1, offset: 0, limit: 20 },
          isLoading: false,
        };
      }
      if (key === "bulk-import-jobs") {
        return {
          data: { items: [], total: 0, offset: 0, limit: 20 },
          isLoading: false,
        };
      }
      return { data: { items: [], total: 0, offset: 0, limit: 50 }, isLoading: false };
    });
    render(<BulkImportTable />);
    const row = screen.getByText("google_drive").closest("tr");
    expect(row).toBeTruthy();
    fireEvent.click(row!);
    expect(
      screen.getByText("Job tracking was added after this import. Per-document status is not available."),
    ).toBeInTheDocument();
  });
});
