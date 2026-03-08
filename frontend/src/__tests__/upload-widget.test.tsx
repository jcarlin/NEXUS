import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUppy = { on: vi.fn(), off: vi.fn(), close: vi.fn() };

vi.mock("@uppy/react", () => ({
  Dashboard: (props: Record<string, unknown>) => (
    <div data-testid="uppy-dashboard" data-theme={props.theme} data-note={props.note}>
      Uppy Dashboard
    </div>
  ),
}));

vi.mock("@/hooks/use-uppy", () => ({
  useUppy: () => mockUppy,
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1" }),
    {
      getState: () => ({ matterId: "matter-1" }),
    },
  ),
}));

import { UploadWidget } from "@/components/documents/upload-widget";

describe("UploadWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Uppy Dashboard component", () => {
    render(<UploadWidget />);
    expect(screen.getByTestId("uppy-dashboard")).toBeInTheDocument();
  });

  it("passes 'dark' theme to Dashboard", () => {
    render(<UploadWidget />);
    const dashboard = screen.getByTestId("uppy-dashboard");
    expect(dashboard).toHaveAttribute("data-theme", "dark");
  });

  it("passes file type note to Dashboard", () => {
    render(<UploadWidget />);
    const dashboard = screen.getByTestId("uppy-dashboard");
    expect(dashboard).toHaveAttribute(
      "data-note",
      "PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT, ZIP, images. Max 500 MB.",
    );
  });

  it("renders Dashboard text content", () => {
    render(<UploadWidget />);
    expect(screen.getByText("Uppy Dashboard")).toBeInTheDocument();
  });

  it("renders without errors when datasetId is provided", () => {
    render(<UploadWidget datasetId="ds-1" />);
    expect(screen.getByTestId("uppy-dashboard")).toBeInTheDocument();
  });

  it("renders without errors when datasetId is null", () => {
    render(<UploadWidget datasetId={null} />);
    expect(screen.getByTestId("uppy-dashboard")).toBeInTheDocument();
  });

  it("renders without errors when onUploadComplete is provided", () => {
    const onComplete = vi.fn();
    render(<UploadWidget onUploadComplete={onComplete} />);
    expect(screen.getByTestId("uppy-dashboard")).toBeInTheDocument();
  });

  it("renders without errors when no props are provided", () => {
    render(<UploadWidget />);
    expect(screen.getByTestId("uppy-dashboard")).toBeInTheDocument();
  });

  it("renders as a single dashboard element", () => {
    render(<UploadWidget />);
    const dashboards = screen.getAllByTestId("uppy-dashboard");
    expect(dashboards).toHaveLength(1);
  });

  it("does not render any loading state", () => {
    render(<UploadWidget />);
    expect(screen.queryByText("Loading")).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
