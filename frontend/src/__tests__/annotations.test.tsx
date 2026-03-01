import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ---- Mocks ---- //

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({ accessToken: "test-token" }),
  },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1", findings: [] }),
    {
      getState: () => ({ matterId: "matter-1", findings: [] }),
    },
  ),
}));

vi.mock("@/lib/auth", () => ({
  isTokenExpired: () => false,
  refreshAccessToken: vi.fn(),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

import type { Annotation } from "@/types";

const makeAnnotation = (overrides: Partial<Annotation> = {}): Annotation => ({
  id: "ann-1",
  document_id: "doc-1",
  matter_id: "matter-1",
  user_id: "user-1",
  page_number: 1,
  annotation_type: "highlight",
  content: "Test annotation",
  anchor: { x: 10, y: 20, width: 30, height: 15 },
  color: "rgba(255, 230, 0, 0.3)",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

// ---- Test 1: Annotation layer renders positioned rectangles ---- //

import { AnnotationLayer } from "@/components/documents/annotation-layer";

describe("AnnotationLayer", () => {
  it("renders positioned rectangles for annotations on the current page", () => {
    const annotations = [
      makeAnnotation({ id: "a1", page_number: 1, content: "First" }),
      makeAnnotation({ id: "a2", page_number: 2, content: "Second" }),
      makeAnnotation({ id: "a3", page_number: 1, content: "Third" }),
    ];

    render(
      <AnnotationLayer
        pageNumber={1}
        annotations={annotations}
        onAnnotationClick={vi.fn()}
      />,
    );

    const rects = screen.getAllByTestId("annotation-rect");
    // Only page 1 annotations should render (a1 and a3)
    expect(rects).toHaveLength(2);
  });

  it("applies correct positioning styles from anchor", () => {
    const annotations = [
      makeAnnotation({
        anchor: { x: 15, y: 25, width: 40, height: 10 },
      }),
    ];

    render(
      <AnnotationLayer pageNumber={1} annotations={annotations} />,
    );

    const rect = screen.getByTestId("annotation-rect");
    expect(rect.style.left).toBe("15%");
    expect(rect.style.top).toBe("25%");
    expect(rect.style.width).toBe("40%");
    expect(rect.style.height).toBe("10%");
  });

  it("calls onAnnotationClick when an annotation is clicked", async () => {
    const onClick = vi.fn();
    const annotations = [makeAnnotation()];

    render(
      <AnnotationLayer
        pageNumber={1}
        annotations={annotations}
        onAnnotationClick={onClick}
      />,
    );

    const rect = screen.getByTestId("annotation-rect");
    fireEvent.click(rect);

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick).toHaveBeenCalledWith(annotations[0]);
  });
});

// ---- Test 2: Annotation panel renders list ---- //

// Mock tanstack query
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn().mockReturnValue({ data: undefined, isLoading: false }),
  useMutation: vi.fn().mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  }),
  useQueryClient: vi.fn().mockReturnValue({
    invalidateQueries: vi.fn(),
  }),
}));

import { AnnotationPanel } from "@/components/documents/annotation-panel";

describe("AnnotationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a list of annotations grouped by page", () => {
    const annotations = [
      makeAnnotation({ id: "a1", page_number: 1, content: "First note" }),
      makeAnnotation({ id: "a2", page_number: 2, content: "Second note", annotation_type: "note" }),
    ];

    render(
      <AnnotationPanel
        documentId="doc-1"
        annotations={annotations}
        onSelectAnnotation={vi.fn()}
      />,
    );

    expect(screen.getByText("First note")).toBeInTheDocument();
    expect(screen.getByText("Second note")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();
  });

  it("shows empty state when no annotations exist", () => {
    render(
      <AnnotationPanel
        documentId="doc-1"
        annotations={[]}
        onSelectAnnotation={vi.fn()}
      />,
    );

    expect(screen.getByText(/No annotations yet/)).toBeInTheDocument();
  });

  it("renders create annotation form", () => {
    render(
      <AnnotationPanel
        documentId="doc-1"
        annotations={[]}
        onSelectAnnotation={vi.fn()}
      />,
    );

    expect(screen.getByText("Add Annotation")).toBeInTheDocument();
    expect(screen.getByLabelText("Content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("shows edit and delete action buttons for each annotation", () => {
    const annotations = [
      makeAnnotation({ id: "a1", content: "Deletable note" }),
    ];

    render(
      <AnnotationPanel
        documentId="doc-1"
        annotations={annotations}
        onSelectAnnotation={vi.fn()}
      />,
    );

    // The annotation row should have icon-sized action buttons (h-6 w-6)
    const buttons = screen.getAllByRole("button");
    // Filter to the small action buttons (edit + delete) — they have the h-6 class
    const actionButtons = buttons.filter((b) => b.className.includes("h-6"));
    // Should have at least 2 action buttons (edit + delete)
    expect(actionButtons.length).toBeGreaterThanOrEqual(2);
  });
});
