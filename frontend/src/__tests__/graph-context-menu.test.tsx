import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { GraphControls } from "@/components/entities/graph-controls";

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: vi.fn((selector: (s: { user: { role: string } | null }) => unknown) =>
    selector({ user: { role: "admin" } }),
  ),
}));

describe("GraphControls edit mode", () => {
  const baseProps = {
    activeTypes: new Set(["person", "organization"]),
    onToggleType: vi.fn(),
    onZoomIn: vi.fn(),
    onZoomOut: vi.fn(),
    onFitView: vi.fn(),
  };

  it("shows edit mode toggle for admin users", () => {
    const onToggleEditMode = vi.fn();
    render(<GraphControls {...baseProps} editMode={false} onToggleEditMode={onToggleEditMode} />);

    const editBtn = screen.getByTitle("Enter edit mode");
    expect(editBtn).toBeInTheDocument();
  });

  it("hides edit mode toggle when onToggleEditMode is not provided", () => {
    render(<GraphControls {...baseProps} />);

    expect(screen.queryByTitle("Enter edit mode")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Exit edit mode")).not.toBeInTheDocument();
  });
});
