import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { KeyboardShortcutsDialog } from "@/components/ui/keyboard-shortcuts-dialog";

describe("KeyboardShortcutsDialog", () => {
  it("does not render content when closed", () => {
    render(
      <KeyboardShortcutsDialog open={false} onOpenChange={vi.fn()} />,
    );
    expect(screen.queryByTestId("keyboard-shortcuts-dialog")).not.toBeInTheDocument();
  });

  it("renders dialog content when open", () => {
    render(
      <KeyboardShortcutsDialog open={true} onOpenChange={vi.fn()} />,
    );
    expect(screen.getByTestId("keyboard-shortcuts-dialog")).toBeInTheDocument();
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
  });

  it("lists shortcut groups", () => {
    render(
      <KeyboardShortcutsDialog open={true} onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("Global")).toBeInTheDocument();
    expect(screen.getByText("Chat / Citation Sidebar")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("Document Viewer")).toBeInTheDocument();
  });

  it("lists global shortcuts", () => {
    render(
      <KeyboardShortcutsDialog open={true} onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("Open command palette")).toBeInTheDocument();
    expect(screen.getByText("New chat")).toBeInTheDocument();
    expect(screen.getByText("Focus search")).toBeInTheDocument();
    expect(screen.getByText("Show keyboard shortcuts")).toBeInTheDocument();
  });

  it("lists review shortcuts", () => {
    render(
      <KeyboardShortcutsDialog open={true} onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("Navigate down / up in list")).toBeInTheDocument();
    expect(screen.getByText("Open selected document")).toBeInTheDocument();
    expect(screen.getByText("Toggle relevance tag")).toBeInTheDocument();
    expect(screen.getByText("Toggle privilege status")).toBeInTheDocument();
  });

  it("calls onOpenChange when close button is clicked", () => {
    const onOpenChange = vi.fn();
    render(
      <KeyboardShortcutsDialog open={true} onOpenChange={onOpenChange} />,
    );
    const closeButton = screen.getByRole("button", { name: "Close" });
    fireEvent.click(closeButton);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
