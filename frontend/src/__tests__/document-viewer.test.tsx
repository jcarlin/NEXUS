import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { detectDocumentType } from "@/lib/utils";

// ---- Mocks ---- //

vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pdf-document">{children}</div>
  ),
  Page: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-page">Page {pageNumber}</div>
  ),
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("@/components/documents/annotation-layer", () => ({
  AnnotationLayer: () => <div data-testid="annotation-layer" />,
}));

// ---- Test 1: detectDocumentType ---- //

describe("detectDocumentType", () => {
  it("returns pdf for type=pdf", () => {
    expect(detectDocumentType("pdf", "doc.pdf")).toBe("pdf");
  });

  it("returns pdf for type=PDF (case-insensitive)", () => {
    expect(detectDocumentType("PDF", "doc.anything")).toBe("pdf");
  });

  it("returns text for type=text", () => {
    expect(detectDocumentType("text", "readme.txt")).toBe("text");
  });

  it("returns text for type=csv", () => {
    expect(detectDocumentType("csv", "data.csv")).toBe("text");
  });

  it("returns text for type=html", () => {
    expect(detectDocumentType("html", "page.html")).toBe("text");
  });

  it("returns image for type=image", () => {
    expect(detectDocumentType("image", "photo.png")).toBe("image");
  });

  it("returns image for type=jpg", () => {
    expect(detectDocumentType("jpg", "photo.jpg")).toBe("image");
  });

  it("returns email for type=eml", () => {
    expect(detectDocumentType("eml", "message.eml")).toBe("email");
  });

  it("returns email for type=email", () => {
    expect(detectDocumentType("email", "message.eml")).toBe("email");
  });

  it("falls back to filename extension for txt", () => {
    expect(detectDocumentType(null, "readme.txt")).toBe("text");
  });

  it("falls back to filename extension for csv", () => {
    expect(detectDocumentType(undefined, "data.csv")).toBe("text");
  });

  it("falls back to filename extension for md", () => {
    expect(detectDocumentType(null, "README.md")).toBe("text");
  });

  it("falls back to filename extension for png", () => {
    expect(detectDocumentType(null, "screenshot.png")).toBe("image");
  });

  it("falls back to filename extension for jpg", () => {
    expect(detectDocumentType(null, "photo.JPG")).toBe("image");
  });

  it("falls back to filename extension for eml", () => {
    expect(detectDocumentType(null, "email.eml")).toBe("email");
  });

  it("falls back to filename extension for pdf", () => {
    expect(detectDocumentType(null, "document.pdf")).toBe("pdf");
  });

  it("returns unknown for unrecognized type and extension", () => {
    expect(detectDocumentType(null, "file.xyz")).toBe("unknown");
  });

  it("returns unknown for null type and no extension", () => {
    expect(detectDocumentType(null, "noextension")).toBe("unknown");
  });

  it("returns unknown for undefined type and no extension", () => {
    expect(detectDocumentType(undefined, "noextension")).toBe("unknown");
  });
});

// ---- Test 2: TextViewer ---- //

import { TextViewer } from "@/components/documents/text-viewer";

describe("TextViewer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches and renders text content", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("Hello, this is document text."),
    });

    render(<TextViewer url="https://example.com/file.txt" />);

    await waitFor(() => {
      expect(screen.getByText("Hello, this is document text.")).toBeInTheDocument();
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://example.com/file.txt",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("shows error state on fetch failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    });

    render(<TextViewer url="https://example.com/missing.txt" />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load (404)")).toBeInTheDocument();
    });
  });
});

// ---- Test 3: ImageViewer ---- //

import { ImageViewer } from "@/components/documents/image-viewer";

describe("ImageViewer", () => {
  it("renders img element with correct src and alt", () => {
    render(<ImageViewer url="https://example.com/photo.png" filename="photo.png" />);

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "https://example.com/photo.png");
    expect(img).toHaveAttribute("alt", "photo.png");
  });

  it("has zoom controls", () => {
    render(<ImageViewer url="https://example.com/photo.png" filename="photo.png" />);

    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("zooms in when clicking zoom-in button", async () => {
    const user = userEvent.setup();
    render(<ImageViewer url="https://example.com/photo.png" filename="photo.png" />);

    // Find the zoom in button (second button with ZoomIn icon)
    const buttons = screen.getAllByRole("button");
    const zoomInBtn = buttons[1]!; // ZoomOut is first, ZoomIn is second
    await user.click(zoomInBtn);

    expect(screen.getByText("125%")).toBeInTheDocument();
  });
});

// ---- Test 4: EmailViewer ---- //

import { EmailViewer } from "@/components/documents/email-viewer";

describe("EmailViewer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parses and renders email headers and body", async () => {
    const rawEml = [
      "From: alice@example.com",
      "To: bob@example.com",
      "Subject: Test Email",
      "Date: Mon, 1 Jan 2024 12:00:00 +0000",
      "",
      "This is the email body.",
      "Second line.",
    ].join("\r\n");

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(rawEml),
    });

    render(<EmailViewer url="https://example.com/message.eml" />);

    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    });

    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
    expect(screen.getByText("Test Email")).toBeInTheDocument();
    expect(screen.getByText(/This is the email body/)).toBeInTheDocument();
  });

  it("handles RFC 2822 folded headers", async () => {
    const rawEml = [
      "From: alice@example.com",
      "Subject: This is a very long",
      "  subject line that wraps",
      "",
      "Body text.",
    ].join("\r\n");

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(rawEml),
    });

    render(<EmailViewer url="https://example.com/message.eml" />);

    await waitFor(() => {
      expect(screen.getByText("This is a very long subject line that wraps")).toBeInTheDocument();
    });
  });

  it("shows error state on fetch failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    render(<EmailViewer url="https://example.com/bad.eml" />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load (500)")).toBeInTheDocument();
    });
  });
});

// ---- Test 5: DocumentViewer routing ---- //

import { DocumentViewer } from "@/components/documents/document-viewer";

describe("DocumentViewer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders PdfViewer for PDF documents", () => {
    render(
      <DocumentViewer
        url="https://example.com/doc.pdf"
        filename="doc.pdf"
        type="pdf"
      />,
    );

    expect(screen.getByTestId("pdf-document")).toBeInTheDocument();
  });

  it("renders TextViewer for text documents", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("text content"),
    });

    render(
      <DocumentViewer
        url="https://example.com/readme.txt"
        filename="readme.txt"
        type="text"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("text content")).toBeInTheDocument();
    });
  });

  it("renders ImageViewer for image documents", () => {
    render(
      <DocumentViewer
        url="https://example.com/photo.png"
        filename="photo.png"
        type="image"
      />,
    );

    expect(screen.getByRole("img")).toHaveAttribute("src", "https://example.com/photo.png");
  });

  it("renders EmailViewer for email documents", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("From: test@test.com\r\n\r\nBody"),
    });

    render(
      <DocumentViewer
        url="https://example.com/mail.eml"
        filename="mail.eml"
        type="eml"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("test@test.com")).toBeInTheDocument();
    });
  });

  it("renders UnsupportedViewer for unknown types", () => {
    render(
      <DocumentViewer
        url="https://example.com/file.xyz"
        filename="file.xyz"
        type="xyz"
      />,
    );

    expect(screen.getByText(/Preview not available/)).toBeInTheDocument();
  });

  it("uses filename fallback when type is null", () => {
    render(
      <DocumentViewer
        url="https://example.com/doc.pdf"
        filename="doc.pdf"
        type={null}
      />,
    );

    expect(screen.getByTestId("pdf-document")).toBeInTheDocument();
  });
});
