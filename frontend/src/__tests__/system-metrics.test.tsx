import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ---- Mocks ---- //

let mockAuthState: Record<string, unknown> = {};

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector(mockAuthState),
    {
      getState: () => mockAuthState,
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

import { SystemMetrics } from "@/components/dashboard/system-metrics";

// ---- Helpers ---- //

function makeMetrics(overrides: Record<string, number> = {}) {
  return {
    cpu_percent: 45,
    memory_used_mb: 8192,
    memory_total_mb: 16384,
    memory_percent: 50,
    disk_used_gb: 120,
    disk_total_gb: 500,
    disk_percent: 24,
    ...overrides,
  };
}

// ---- Tests ---- //

describe("SystemMetrics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState = { user: { role: "admin" } };
    mockUseQuery.mockReturnValue({ data: undefined });
  });

  it("renders nothing for non-admin user", () => {
    mockAuthState = { user: { role: "viewer" } };
    const { container } = render(<SystemMetrics />);
    expect(container.innerHTML).toBe("");
  });

  it("renders three metrics for admin user", () => {
    mockUseQuery.mockReturnValue({ data: makeMetrics() });

    render(<SystemMetrics />);

    // CPU label and percentage
    expect(screen.getByText("CPU")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();

    // Memory label and usage (8192 MB = 8.0 GB / 16384 MB = 16.0 GB)
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("8.0 GB / 16.0 GB")).toBeInTheDocument();

    // Disk label and usage
    expect(screen.getByText("Disk")).toBeInTheDocument();
    expect(screen.getByText("120 / 500 GB")).toBeInTheDocument();
  });

  it("shows amber color for values between 70-90%", () => {
    mockUseQuery.mockReturnValue({
      data: makeMetrics({ memory_percent: 85 }),
    });

    render(<SystemMetrics />);

    // The memory detail text should have the amber class
    const memoryDetail = screen.getByText("8.0 GB / 16.0 GB");
    expect(memoryDetail.className).toMatch(/text-amber-500/);
  });

  it("shows red color for values above 90%", () => {
    mockUseQuery.mockReturnValue({
      data: makeMetrics({ disk_percent: 95 }),
    });

    render(<SystemMetrics />);

    // The disk detail text should have the red class
    const diskDetail = screen.getByText("120 / 500 GB");
    expect(diskDetail.className).toMatch(/text-red-500/);
  });

  it("renders nothing when API fails", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isError: true });

    const { container } = render(<SystemMetrics />);
    expect(container.innerHTML).toBe("");
  });
});
