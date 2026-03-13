import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuditLogTable } from "@/components/admin/audit-log-table";
import type { AuditLogEntry } from "@/types";

// Mock apiFetchRaw for server-side export
const mockApiFetchRaw = vi.fn();
vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
  apiFetchRaw: (...args: unknown[]) => mockApiFetchRaw(...args),
}));

// jsdom does not provide URL.createObjectURL/revokeObjectURL
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

const MOCK_ENTRIES: AuditLogEntry[] = [
  {
    id: "1",
    user_email: "admin@test.com",
    action: "GET",
    resource: "/api/v1/documents",
    status_code: 200,
    ip_address: "127.0.0.1",
    duration_ms: 50,
    created_at: "2024-03-01T10:00:00Z",
    matter_id: null,
    user_id: null,
  } as AuditLogEntry,
];

describe("AuditLogTable export dialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Polyfill URL.createObjectURL/revokeObjectURL for jsdom
    URL.createObjectURL = vi.fn(() => "blob:test-url");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  });

  it("renders server export button", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    expect(screen.getByTestId("server-export-button")).toBeInTheDocument();
    expect(screen.getByText("Export")).toBeInTheDocument();
  });

  it("opens export dialog when export button is clicked", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));
    expect(screen.getByTestId("audit-export-dialog")).toBeInTheDocument();
    expect(screen.getByText("Export Audit Logs")).toBeInTheDocument();
  });

  it("export dialog shows format, table, and date selectors", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));

    expect(screen.getByText("Log Table")).toBeInTheDocument();
    expect(screen.getByText("Format")).toBeInTheDocument();
    expect(screen.getByText("Start Date")).toBeInTheDocument();
    expect(screen.getByText("End Date")).toBeInTheDocument();
  });

  it("export dialog has submit and cancel buttons", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));

    expect(screen.getByTestId("export-submit")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("clicking cancel closes the dialog", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));
    expect(screen.getByTestId("audit-export-dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByTestId("audit-export-dialog")).not.toBeInTheDocument();
  });

  it("submit calls apiFetchRaw with correct params", async () => {
    const mockBlob = new Blob(["test"], { type: "text/csv" });
    mockApiFetchRaw.mockResolvedValue({
      blob: () => Promise.resolve(mockBlob),
    });

    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));

    // Click export with defaults (csv, audit_log, no date range)
    fireEvent.click(screen.getByTestId("export-submit"));

    await waitFor(() => {
      expect(mockApiFetchRaw).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/admin/audit/export?"),
      );
    });

    const calledUrl = mockApiFetchRaw.mock.calls[0][0] as string;
    expect(calledUrl).toContain("format=csv");
    expect(calledUrl).toContain("table=audit_log");
  });

  it("export dialog has date inputs that accept values", () => {
    render(<AuditLogTable data={MOCK_ENTRIES} isLoading={false} />);
    fireEvent.click(screen.getByTestId("server-export-button"));

    const startDate = screen.getByTestId("export-start-date") as HTMLInputElement;
    const endDate = screen.getByTestId("export-end-date") as HTMLInputElement;

    fireEvent.change(startDate, { target: { value: "2024-01-01" } });
    fireEvent.change(endDate, { target: { value: "2024-12-31" } });

    expect(startDate.value).toBe("2024-01-01");
    expect(endDate.value).toBe("2024-12-31");
  });
});
