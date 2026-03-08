import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, unknown>;
  }) => (
    <a href={props.to} data-params={JSON.stringify(props.params)}>
      {children}
    </a>
  ),
}));

import { EntityTable } from "@/components/entities/entity-table";
import type { EntityResponse } from "@/types";

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

const MOCK_ENTITIES: EntityResponse[] = [
  {
    id: "e-1",
    name: "John Smith",
    type: "person",
    aliases: ["J. Smith"],
    first_seen: "2024-01-15T00:00:00Z",
    mention_count: 42,
  },
  {
    id: "e-2",
    name: "Acme Corp",
    type: "organization",
    aliases: [],
    first_seen: "2024-02-01T00:00:00Z",
    mention_count: 28,
  },
  {
    id: "e-3",
    name: "New York",
    type: "location",
    aliases: ["NYC"],
    first_seen: null,
    mention_count: 15,
  },
  {
    id: "e-4",
    name: "January 2024",
    type: "date",
    aliases: [],
    first_seen: "2024-01-01T00:00:00Z",
    mention_count: 8,
  },
  {
    id: "e-5",
    name: "$1,000,000",
    type: "monetary_amount",
    aliases: [],
    first_seen: null,
    mention_count: 3,
  },
];

describe("EntityTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders table with column headers", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Mentions")).toBeInTheDocument();
    expect(screen.getByText("First Seen")).toBeInTheDocument();
  });

  it("shows 'No entities found.' when data is empty", () => {
    render(
      <Wrapper>
        <EntityTable data={[]} />
      </Wrapper>,
    );
    expect(screen.getByText("No entities found.")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading=true", () => {
    const { container } = render(
      <Wrapper>
        <EntityTable data={[]} loading />
      </Wrapper>,
    );
    // Skeletons are div elements
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders entity names", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    expect(screen.getByText("John Smith")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("New York")).toBeInTheDocument();
  });

  it("renders entity names as links to /entities/$id", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    const link = screen.getByText("John Smith").closest("a");
    expect(link).toHaveAttribute("href", "/entities/$id");
    expect(link).toHaveAttribute(
      "data-params",
      JSON.stringify({ id: "e-1" }),
    );
  });

  it("shows type badges with correct text", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    expect(screen.getByText("person")).toBeInTheDocument();
    expect(screen.getByText("organization")).toBeInTheDocument();
    expect(screen.getByText("location")).toBeInTheDocument();
    expect(screen.getByText("date")).toBeInTheDocument();
    expect(screen.getByText("monetary_amount")).toBeInTheDocument();
  });

  it("renders mention counts", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  it("renders first seen dates when available", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    // formatDate("2024-01-15T00:00:00Z") renders a locale-dependent date string
    // Check that the formatted date is present (may vary by locale)
    const formatted = new Date("2024-01-15T00:00:00Z").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    expect(screen.getByText(formatted)).toBeInTheDocument();
  });

  it("shows '--' for missing first_seen", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("renders search toolbar", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    expect(
      screen.getByPlaceholderText("Search entities..."),
    ).toBeInTheDocument();
  });

  it("does not show table when loading", () => {
    render(
      <Wrapper>
        <EntityTable data={[]} loading />
      </Wrapper>,
    );
    expect(screen.queryByText("Name")).not.toBeInTheDocument();
    expect(screen.queryByText("No entities found.")).not.toBeInTheDocument();
  });

  it("renders correct number of data rows", () => {
    render(
      <Wrapper>
        <EntityTable data={MOCK_ENTITIES} />
      </Wrapper>,
    );
    // 5 entities + 1 header row
    const rows = screen.getAllByRole("row");
    // header row + 5 data rows
    expect(rows).toHaveLength(6);
  });
});
