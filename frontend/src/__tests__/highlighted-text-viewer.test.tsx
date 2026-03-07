import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

import { HighlightedTextViewer } from "@/components/documents/highlighted-text-viewer";

describe("HighlightedTextViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default mock: successful fetch
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("This is a document with important terms in it."),
    }) as unknown as typeof fetch;
  });

  it("renders content after loading", async () => {
    render(<HighlightedTextViewer url="https://example.com/doc.txt" />);

    await waitFor(() => {
      expect(screen.getByText(/This is a document/)).toBeInTheDocument();
    });
  });

  it("highlights matching text with <mark>", async () => {
    render(
      <HighlightedTextViewer
        url="https://example.com/doc.txt"
        highlightText="important terms"
      />,
    );

    await waitFor(() => {
      const mark = screen.getByText("important terms");
      expect(mark.tagName).toBe("MARK");
      expect(mark).toHaveClass("citation-highlight");
    });
  });

  it("handles case-insensitive matching", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("The IMPORTANT TERMS are defined here."),
    }) as unknown as typeof fetch;

    render(
      <HighlightedTextViewer
        url="https://example.com/doc.txt"
        highlightText="important terms"
      />,
    );

    await waitFor(() => {
      const mark = screen.getByText("IMPORTANT TERMS");
      expect(mark.tagName).toBe("MARK");
    });
  });

  it("degrades gracefully when no match found", async () => {
    render(
      <HighlightedTextViewer
        url="https://example.com/doc.txt"
        highlightText="nonexistent phrase that does not appear"
      />,
    );

    await waitFor(() => {
      // Content should still render, just without highlight
      expect(screen.getByText(/This is a document/)).toBeInTheDocument();
      expect(screen.queryByRole("mark")).not.toBeInTheDocument();
    });
  });

  it("shows error on fetch failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }) as unknown as typeof fetch;

    render(<HighlightedTextViewer url="https://example.com/missing.txt" />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to load/)).toBeInTheDocument();
    });
  });

  it("auto-scrolls highlighted text into view", async () => {
    render(
      <HighlightedTextViewer
        url="https://example.com/doc.txt"
        highlightText="important terms"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("important terms")).toBeInTheDocument();
    });

    // Wait for the scroll timeout
    await waitFor(
      () => {
        expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
      },
      { timeout: 500 },
    );
  });

  it("shows skeleton while loading", () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})) as unknown as typeof fetch;

    const { container } = render(
      <HighlightedTextViewer url="https://example.com/doc.txt" />,
    );

    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });
});
