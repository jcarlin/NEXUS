import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { FileText, Users, Flame, Loader2 } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";

describe("StatCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders title", () => {
    render(<StatCard title="Documents" value={42} icon={FileText} />);
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("renders numeric value", () => {
    render(<StatCard title="Documents" value={42} icon={FileText} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders string value", () => {
    render(<StatCard title="Status" value="Active" icon={FileText} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(
      <StatCard
        title="Documents"
        value={42}
        icon={FileText}
        description="Total ingested"
      />,
    );
    expect(screen.getByText("Total ingested")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    render(<StatCard title="Documents" value={42} icon={FileText} />);
    expect(screen.queryByText("Total ingested")).not.toBeInTheDocument();
  });

  it("shows skeleton when loading", () => {
    const { container } = render(
      <StatCard title="Documents" value={42} icon={FileText} loading />,
    );
    // Value should not be visible
    expect(screen.queryByText("42")).not.toBeInTheDocument();
    // Skeleton should be present
    const skeleton = container.querySelector('[class*="animate-pulse"]');
    expect(skeleton).toBeTruthy();
  });

  it("shows value when not loading", () => {
    render(
      <StatCard title="Documents" value={42} icon={FileText} loading={false} />,
    );
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders 0 as a valid value", () => {
    render(<StatCard title="Processing" value={0} icon={Loader2} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("renders with different icons", () => {
    const { rerender } = render(
      <StatCard title="Documents" value={1} icon={FileText} />,
    );
    expect(screen.getByText("Documents")).toBeInTheDocument();

    rerender(<StatCard title="Entities" value={2} icon={Users} />);
    expect(screen.getByText("Entities")).toBeInTheDocument();

    rerender(<StatCard title="Hot Docs" value={3} icon={Flame} />);
    expect(screen.getByText("Hot Docs")).toBeInTheDocument();
  });

  it("renders inside a Card component structure", () => {
    const { container } = render(
      <StatCard title="Test" value={0} icon={FileText} />,
    );
    // Should have a Card wrapper (div with role or class)
    expect(container.firstElementChild).toBeTruthy();
  });

  it("shows description even when loading", () => {
    render(
      <StatCard
        title="Documents"
        value={42}
        icon={FileText}
        description="Total ingested"
        loading
      />,
    );
    expect(screen.getByText("Total ingested")).toBeInTheDocument();
  });

  it("renders large numbers correctly", () => {
    render(<StatCard title="Documents" value={50000} icon={FileText} />);
    expect(screen.getByText("50000")).toBeInTheDocument();
  });
});
