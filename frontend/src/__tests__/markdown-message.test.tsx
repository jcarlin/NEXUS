import { describe, it, expect, vi } from "vitest";
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
    search?: Record<string, unknown>;
  }) => <a href={props.to}>{children}</a>,
}));

import { MarkdownMessage } from "@/components/chat/markdown-message";

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

describe("MarkdownMessage", () => {
  it("renders plain text as a paragraph", () => {
    render(<MarkdownMessage content="Hello world" sources={[]} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders bold text", () => {
    render(<MarkdownMessage content="This is **bold** text" sources={[]} />, {
      wrapper: Wrapper,
    });
    const bold = screen.getByText("bold");
    expect(bold.tagName).toBe("STRONG");
  });

  it("renders headers", () => {
    render(<MarkdownMessage content="## Section Title" sources={[]} />, {
      wrapper: Wrapper,
    });
    const header = screen.getByText("Section Title");
    expect(header.tagName).toBe("H2");
  });

  it("renders unordered lists", () => {
    const { container } = render(
      <MarkdownMessage content={"- Item one\n- Item two\n- Item three"} sources={[]} />,
      { wrapper: Wrapper },
    );
    const listItems = container.querySelectorAll("li");
    expect(listItems.length).toBeGreaterThanOrEqual(1);
    expect(container.textContent).toContain("Item one");
    expect(container.textContent).toContain("Item two");
    expect(container.textContent).toContain("Item three");
  });

  it("renders inline code", () => {
    render(
      <MarkdownMessage content="Use `console.log` for debugging" sources={[]} />,
      { wrapper: Wrapper },
    );
    const code = screen.getByText("console.log");
    expect(code.tagName).toBe("CODE");
  });

  it("renders citation markers for [N] patterns", () => {
    const sources = [
      {
        id: "doc-1",
        filename: "memo.pdf",
        page: 3,
        chunk_text: "Relevant excerpt.",
        relevance_score: 0.9,
      },
    ];
    render(
      <MarkdownMessage
        content="The evidence shows [1] that the claim is valid."
        sources={sources}
      />,
      { wrapper: Wrapper },
    );
    // Citation marker renders the 1-indexed number
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/The evidence shows/)).toBeInTheDocument();
  });

  it("renders tables with GFM", () => {
    const table = "| Name | Role |\n|------|------|\n| Alice | CEO |\n| Bob | CTO |";
    render(<MarkdownMessage content={table} sources={[]} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("CEO")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("renders blockquotes", () => {
    render(
      <MarkdownMessage content="> This is a quote" sources={[]} />,
      { wrapper: Wrapper },
    );
    expect(screen.getByText("This is a quote")).toBeInTheDocument();
  });

  it("renders links with target _blank", () => {
    render(
      <MarkdownMessage content="Visit [Example](https://example.com)" sources={[]} />,
      { wrapper: Wrapper },
    );
    const link = screen.getByText("Example");
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
