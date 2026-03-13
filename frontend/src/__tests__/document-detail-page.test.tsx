import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => {
    routeOptions._useParams = () => ({ id: "doc-123" });
    return routeOptions;
  },
  Link: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    to: string;
  }) => <a href={props.to}>{children}</a>,
}));

// After import, patch useSearch onto the route object


vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/hooks/use-document-download", () => ({
  useDocumentDownload: () => ({ downloadUrl: null, filename: null }),
}));

vi.mock("@/hooks/use-feature-flags", () => ({
  useFeatureFlag: () => false,
}));

vi.mock("@/hooks/use-annotations", () => ({
  useAnnotations: () => ({ data: { items: [] } }),
}));

vi.mock("@/components/documents/document-viewer", () => ({
  DocumentViewer: () => <div data-testid="document-viewer">Viewer</div>,
}));

vi.mock("@/components/documents/metadata-panel", () => ({
  MetadataPanel: ({ doc }: { doc: { filename: string } }) => (
    <div data-testid="metadata-panel">{doc.filename}</div>
  ),
}));

vi.mock("@/components/documents/annotation-panel", () => ({
  AnnotationPanel: () => <div data-testid="annotation-panel">Annotations</div>,
}));

vi.mock("@/components/documents/redaction-panel", () => ({
  RedactionPanel: () => <div data-testid="redaction-panel">Redaction</div>,
}));

import { Route } from "@/routes/documents/$id";

// The route uses Route.useParams() and Route.useSearch() — we need to mock them
const routeObj = Route as unknown as {
  component: React.ComponentType;
  useParams: () => { id: string };
  useSearch: () => { page?: number; highlight?: string };
};
routeObj.useParams = () => ({ id: "doc-123" });
routeObj.useSearch = () => ({});

const Component = routeObj.component;

describe("DocumentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("shows loading skeletons when loading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = render(<Component />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows 'Document not found.' when no doc returned", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Document not found.")).toBeInTheDocument();
  });

  it("renders document filename when loaded", () => {
    mockUseQuery.mockReturnValue({
      data: {
        id: "doc-123",
        filename: "contract.pdf",
        type: "pdf",
        page_count: 10,
        chunk_count: 20,
        entity_count: 5,
      },
      isLoading: false,
    });
    render(<Component />);
    const headings = screen.getAllByText("contract.pdf");
    expect(headings.length).toBeGreaterThanOrEqual(1);
    // The h1 should contain the filename
    expect(headings[0]!.tagName).toBe("H1");
  });

  it("renders page/chunk/entity counts", () => {
    mockUseQuery.mockReturnValue({
      data: {
        id: "doc-123",
        filename: "memo.pdf",
        type: "pdf",
        page_count: 10,
        chunk_count: 20,
        entity_count: 5,
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("10 pages | 20 chunks | 5 entities")).toBeInTheDocument();
  });

  it("renders back link to documents list", () => {
    mockUseQuery.mockReturnValue({
      data: {
        id: "doc-123",
        filename: "test.pdf",
        type: "pdf",
        page_count: 1,
        chunk_count: 1,
        entity_count: 0,
      },
      isLoading: false,
    });
    render(<Component />);
    const backLink = screen.getByRole("link", { name: "" });
    expect(backLink).toHaveAttribute("href", "/documents");
  });

  it("renders metadata panel for non-PDF documents", () => {
    mockUseQuery.mockReturnValue({
      data: {
        id: "doc-123",
        filename: "memo.txt",
        type: "txt",
        page_count: 1,
        chunk_count: 1,
        entity_count: 0,
      },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByTestId("metadata-panel")).toBeInTheDocument();
  });
});
