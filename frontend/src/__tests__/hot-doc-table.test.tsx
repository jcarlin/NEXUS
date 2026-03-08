import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

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

vi.mock("@/components/review/sentiment-sparklines", () => ({
  SentimentSparklines: (props: Record<string, unknown>) => (
    <div data-testid="sentiment-sparklines">
      {JSON.stringify(props)}
    </div>
  ),
}));

import { HotDocTable, hotDocScoreColor } from "@/components/review/hot-doc-table";
import type { DocumentDetail } from "@/types";

const MOCK_HOT_DOCS: DocumentDetail[] = [
  {
    id: "doc-1",
    filename: "suspicious-email.eml",
    type: "eml",
    page_count: 1,
    chunk_count: 2,
    entity_count: 5,
    created_at: "2024-03-15T10:00:00Z",
    updated_at: "2024-03-15T10:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: "privileged",
    hot_doc_score: 0.92,
    anomaly_score: 0.75,
    sentiment_positive: 0.1,
    sentiment_negative: 0.8,
    sentiment_pressure: 0.6,
    sentiment_opportunity: null,
    sentiment_rationalization: null,
    sentiment_intent: 0.4,
    sentiment_concealment: 0.3,
    context_gaps: ["Missing timeline data"],
  } as DocumentDetail,
  {
    id: "doc-2",
    filename: "memo.pdf",
    type: "pdf",
    page_count: 5,
    chunk_count: 10,
    entity_count: 3,
    created_at: "2024-03-10T09:00:00Z",
    updated_at: "2024-03-10T09:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: null,
    hot_doc_score: 0.65,
    anomaly_score: 0.3,
    sentiment_positive: 0.5,
    sentiment_negative: 0.2,
    sentiment_pressure: null,
    sentiment_opportunity: null,
    sentiment_rationalization: null,
    sentiment_intent: null,
    sentiment_concealment: null,
    context_gaps: [],
  } as DocumentDetail,
  {
    id: "doc-3",
    filename: "report.docx",
    type: "docx",
    page_count: 20,
    chunk_count: 40,
    entity_count: 12,
    created_at: "2024-03-01T08:00:00Z",
    updated_at: "2024-03-01T08:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: "not_privileged",
    hot_doc_score: 0.45,
    anomaly_score: null,
    sentiment_positive: null,
    sentiment_negative: null,
    sentiment_pressure: null,
    sentiment_opportunity: null,
    sentiment_rationalization: null,
    sentiment_intent: null,
    sentiment_concealment: null,
    context_gaps: [],
  } as DocumentDetail,
];

describe("HotDocTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders column headers", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    expect(screen.getByText("Filename")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Hot Score")).toBeInTheDocument();
    expect(screen.getByText("Anomaly")).toBeInTheDocument();
    expect(screen.getByText("Privilege")).toBeInTheDocument();
    expect(screen.getByText("Date")).toBeInTheDocument();
  });

  it("shows 'No hot documents found.' when empty", () => {
    render(<HotDocTable data={[]} />);
    expect(screen.getByText("No hot documents found.")).toBeInTheDocument();
  });

  it("shows loading skeletons", () => {
    const { container } = render(<HotDocTable data={[]} loading />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders filenames as links", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    const link = screen.getByText("suspicious-email.eml").closest("a");
    expect(link).toHaveAttribute("href", "/documents/$id");
    expect(link).toHaveAttribute(
      "data-params",
      JSON.stringify({ id: "doc-1" }),
    );
  });

  it("renders hot scores with formatting", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    expect(screen.getByText("0.92")).toBeInTheDocument();
    expect(screen.getByText("0.65")).toBeInTheDocument();
    expect(screen.getByText("0.45")).toBeInTheDocument();
  });

  it("renders anomaly scores when present", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    expect(screen.getByText("0.75")).toBeInTheDocument();
    expect(screen.getByText("0.30")).toBeInTheDocument();
  });

  it("shows '--' for missing anomaly scores", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("renders privilege badges", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    expect(screen.getByText("privileged")).toBeInTheDocument();
    expect(screen.getByText("not_privileged")).toBeInTheDocument();
  });

  it("rows are expandable - clicking toggles expanded state", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    // Initially no sentiment sparklines visible
    expect(screen.queryByTestId("sentiment-sparklines")).not.toBeInTheDocument();

    // Click a row to expand
    const row = screen.getByText("suspicious-email.eml").closest("tr")!;
    fireEvent.click(row);

    // Should now show sparklines
    expect(screen.getByTestId("sentiment-sparklines")).toBeInTheDocument();
  });

  it("clicking expanded row collapses it", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    const row = screen.getByText("suspicious-email.eml").closest("tr")!;

    // Expand
    fireEvent.click(row);
    expect(screen.getByTestId("sentiment-sparklines")).toBeInTheDocument();

    // Collapse
    fireEvent.click(row);
    expect(screen.queryByTestId("sentiment-sparklines")).not.toBeInTheDocument();
  });

  it("default sort is hot_doc_score desc (highest first)", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    const rows = screen.getAllByRole("row");
    // First data row (index 1) should have highest score
    const firstDataRow = rows[1]!;
    expect(firstDataRow.textContent).toContain("0.92");
  });

  it("renders search toolbar", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    expect(
      screen.getByPlaceholderText("Search hot documents..."),
    ).toBeInTheDocument();
  });

  it("does not render table when loading", () => {
    render(<HotDocTable data={[]} loading />);
    expect(screen.queryByText("Filename")).not.toBeInTheDocument();
  });

  it("renders correct number of rows", () => {
    render(<HotDocTable data={MOCK_HOT_DOCS} />);
    const rows = screen.getAllByRole("row");
    // 1 header + 3 data rows
    expect(rows).toHaveLength(4);
  });
});

describe("hotDocScoreColor", () => {
  it("returns red for score >= 0.8", () => {
    expect(hotDocScoreColor(0.8)).toContain("text-red");
    expect(hotDocScoreColor(0.95)).toContain("text-red");
  });

  it("returns yellow for score >= 0.5 and < 0.8", () => {
    expect(hotDocScoreColor(0.5)).toContain("text-yellow");
    expect(hotDocScoreColor(0.7)).toContain("text-yellow");
  });

  it("returns muted for score < 0.5", () => {
    expect(hotDocScoreColor(0.3)).toContain("text-muted");
    expect(hotDocScoreColor(0.1)).toContain("text-muted");
  });

  it("returns muted for null/undefined", () => {
    expect(hotDocScoreColor(null)).toContain("text-muted");
    expect(hotDocScoreColor(undefined)).toContain("text-muted");
  });
});
