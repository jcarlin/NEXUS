import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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

import { DocumentTable } from "@/components/documents/document-table";
import type { DocumentResponse } from "@/types";

const MOCK_DOCS: DocumentResponse[] = [
  {
    id: "doc-1",
    filename: "contract.pdf",
    type: "pdf",
    page_count: 12,
    chunk_count: 24,
    entity_count: 8,
    created_at: "2024-03-15T10:00:00Z",
    updated_at: "2024-03-15T10:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: "privileged",
    hot_doc_score: 0.85,
  } as DocumentResponse & { hot_doc_score: number },
  {
    id: "doc-2",
    filename: "memo.docx",
    type: "docx",
    page_count: 3,
    chunk_count: 6,
    entity_count: 2,
    created_at: "2024-03-10T09:00:00Z",
    updated_at: "2024-03-10T09:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: null,
    hot_doc_score: 0.55,
  } as DocumentResponse & { hot_doc_score: number },
  {
    id: "doc-3",
    filename: "notes.txt",
    type: "txt",
    page_count: 1,
    chunk_count: 1,
    entity_count: 0,
    created_at: "2024-03-01T08:00:00Z",
    updated_at: "2024-03-01T08:00:00Z",
    matter_id: "m-1",
    dataset_id: null,
    privilege_status: "not_privileged",
    hot_doc_score: 0.2,
  } as DocumentResponse & { hot_doc_score: number },
];

describe("DocumentTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders column headers", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("Filename")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Pages")).toBeInTheDocument();
    expect(screen.getByText("Hot Score")).toBeInTheDocument();
    expect(screen.getByText("Privilege")).toBeInTheDocument();
    expect(screen.getByText("Date")).toBeInTheDocument();
  });

  it("shows 'No documents found.' when empty", () => {
    render(<DocumentTable data={[]} />);
    expect(screen.getByText("No documents found.")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    const { container } = render(<DocumentTable data={[]} loading />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders filenames as links to /documents/$id", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    const link = screen.getByText("contract.pdf").closest("a");
    expect(link).toHaveAttribute("href", "/documents/$id");
    expect(link).toHaveAttribute(
      "data-params",
      JSON.stringify({ id: "doc-1" }),
    );
  });

  it("renders file extensions as badges", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("PDF")).toBeInTheDocument();
    expect(screen.getByText("DOCX")).toBeInTheDocument();
    expect(screen.getByText("TXT")).toBeInTheDocument();
  });

  it("renders page counts", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders hot scores with correct formatting", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("0.85")).toBeInTheDocument();
    expect(screen.getByText("0.55")).toBeInTheDocument();
    expect(screen.getByText("0.20")).toBeInTheDocument();
  });

  it("applies red color to scores >= 0.8", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    const highScore = screen.getByText("0.85");
    expect(highScore.className).toContain("text-red-400");
  });

  it("applies yellow color to scores >= 0.5 and < 0.8", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    const midScore = screen.getByText("0.55");
    expect(midScore.className).toContain("text-yellow-400");
  });

  it("renders privilege badges", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("privileged")).toBeInTheDocument();
    expect(screen.getByText("not_privileged")).toBeInTheDocument();
  });

  it("renders dates in formatted form", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("Mar 15, 2024")).toBeInTheDocument();
  });

  it("renders correct number of rows", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    const rows = screen.getAllByRole("row");
    // 1 header + 3 data rows
    expect(rows).toHaveLength(4);
  });

  it("does not show table when loading", () => {
    render(<DocumentTable data={[]} loading />);
    expect(screen.queryByText("Filename")).not.toBeInTheDocument();
  });

  it("renders all document filenames", () => {
    render(<DocumentTable data={MOCK_DOCS} />);
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("memo.docx")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
  });
});
