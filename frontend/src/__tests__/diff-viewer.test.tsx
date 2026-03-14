import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { DiffViewer } from "@/components/documents/diff-viewer";

describe("DiffViewer", () => {
  it("renders filenames in header", () => {
    const { container } = render(
      <DiffViewer
        blocks={[]}
        leftFilename="contract_v1.pdf"
        rightFilename="contract_v2.pdf"
      />,
    );
    expect(screen.getByText("contract_v1.pdf")).toBeTruthy();
    expect(screen.getByText("contract_v2.pdf")).toBeTruthy();
  });

  it("renders empty state when no blocks", () => {
    render(
      <DiffViewer blocks={[]} leftFilename="a.pdf" rightFilename="b.pdf" />,
    );
    expect(
      screen.getByText("No differences found between the two documents."),
    ).toBeTruthy();
  });

  it("renders diff blocks with content", () => {
    const blocks = [
      {
        op: "equal" as const,
        left_start: 0,
        left_end: 1,
        right_start: 0,
        right_end: 1,
        left_text: "same line\n",
        right_text: "same line\n",
      },
      {
        op: "replace" as const,
        left_start: 1,
        left_end: 2,
        right_start: 1,
        right_end: 2,
        left_text: "old text\n",
        right_text: "new text\n",
      },
    ];
    render(
      <DiffViewer
        blocks={blocks}
        leftFilename="left.pdf"
        rightFilename="right.pdf"
      />,
    );
    expect(screen.getByText(/old text/)).toBeTruthy();
    expect(screen.getByText(/new text/)).toBeTruthy();
  });

  it("shows truncation warning when truncated", () => {
    render(
      <DiffViewer
        blocks={[]}
        leftFilename="a.pdf"
        rightFilename="b.pdf"
        truncated={true}
      />,
    );
    expect(screen.getByText(/truncated to 50,000 characters/)).toBeTruthy();
  });
});
