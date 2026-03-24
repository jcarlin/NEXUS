import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseFeatureFlags = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useMatchRoute: () => () => false,
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ sidebarCollapsed: false, toggleSidebar: vi.fn() }),
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ user: { role: "admin" } }),
}));

vi.mock("@/hooks/use-feature-flags", () => ({
  useFeatureFlags: () => mockUseFeatureFlags(),
  FeatureFlags: {},
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ComponentPropsWithoutRef<"button">) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children, ...props }: React.ComponentPropsWithoutRef<"div">) => (
    <div {...props}>{children}</div>
  ),
}));

import { Sidebar } from "@/components/layout/sidebar";

describe("Sidebar page visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows all pages when all flags are true", () => {
    mockUseFeatureFlags.mockReturnValue({
      data: {
        page_dashboard: true,
        page_chat: true,
        page_documents: true,
        page_ingest: true,
        page_datasets: true,
        page_entities: true,
        page_comms_matrix: true,
        page_timeline: true,
        page_network_graph: true,
        page_hot_docs: true,
        page_result_set: true,
        page_exports: true,
        page_case_setup: true,
      },
    });
    render(<Sidebar />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Comms Matrix")).toBeInTheDocument();
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
    expect(screen.getByText("Case Setup")).toBeInTheDocument();
  });

  it("hides pages when their flag is false", () => {
    mockUseFeatureFlags.mockReturnValue({
      data: {
        page_dashboard: true,
        page_chat: false,
        page_documents: true,
        page_ingest: true,
        page_datasets: true,
        page_entities: true,
        page_comms_matrix: false,
        page_timeline: true,
        page_network_graph: true,
        page_hot_docs: true,
        page_result_set: true,
        page_exports: true,
        page_case_setup: false,
      },
    });
    render(<Sidebar />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Chat")).not.toBeInTheDocument();
    expect(screen.queryByText("Comms Matrix")).not.toBeInTheDocument();
    expect(screen.queryByText("Case Setup")).not.toBeInTheDocument();
    // Other pages still visible
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
    expect(screen.getByText("Timeline")).toBeInTheDocument();
  });

  it("shows all pages while flags are loading (data undefined)", () => {
    mockUseFeatureFlags.mockReturnValue({ data: undefined });
    render(<Sidebar />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Comms Matrix")).toBeInTheDocument();
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
  });

  it("always shows admin nav items regardless of flags", () => {
    mockUseFeatureFlags.mockReturnValue({
      data: {
        page_dashboard: false,
        page_chat: false,
        page_documents: false,
        page_ingest: false,
        page_datasets: false,
        page_entities: false,
        page_comms_matrix: false,
        page_timeline: false,
        page_network_graph: false,
        page_hot_docs: false,
        page_result_set: false,
        page_exports: false,
        page_case_setup: false,
      },
    });
    render(<Sidebar />);

    // Admin pages have no pageFlag — always visible
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Feature Flags")).toBeInTheDocument();
    expect(screen.getByText("Pages")).toBeInTheDocument();
  });
});
