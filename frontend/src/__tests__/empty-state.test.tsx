import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { EmptyState } from "@/components/ui/empty-state";
import { Search } from "lucide-react";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No results found" />);
    expect(screen.getByText("No results found")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(
      <EmptyState
        title="No data"
        description="Try adjusting your search filters."
      />,
    );
    expect(screen.getByText("Try adjusting your search filters.")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    render(<EmptyState title="No data" />);
    expect(screen.queryByText("Try adjusting")).not.toBeInTheDocument();
  });

  it("renders children (action button)", () => {
    render(
      <EmptyState title="No documents">
        <button>Upload Documents</button>
      </EmptyState>,
    );
    expect(screen.getByText("Upload Documents")).toBeInTheDocument();
  });

  it("accepts custom icon", () => {
    const { container } = render(
      <EmptyState title="No results" icon={Search} />,
    );
    // The Search icon should be rendered as an SVG
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
  });
});
