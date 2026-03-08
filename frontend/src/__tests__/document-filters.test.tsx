import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DocumentFilters } from "@/components/documents/document-filters";

describe("DocumentFilters", () => {
  const onSearchChange = vi.fn();
  const onFileExtensionChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders search input with correct placeholder", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    expect(
      screen.getByPlaceholderText("Search documents..."),
    ).toBeInTheDocument();
  });

  it("displays current search value", () => {
    render(
      <DocumentFilters
        search="contract"
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const input = screen.getByPlaceholderText(
      "Search documents...",
    ) as HTMLInputElement;
    expect(input.value).toBe("contract");
  });

  it("calls onSearchChange when typing", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const input = screen.getByPlaceholderText("Search documents...");
    fireEvent.change(input, { target: { value: "deposition" } });
    expect(onSearchChange).toHaveBeenCalledWith("deposition");
  });

  it("renders file extension select", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    // The select trigger should show "All types" when value is "all"
    expect(screen.getByText("All types")).toBeInTheDocument();
  });

  it("displays selected extension value", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="pdf"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    // When fileExtension is "pdf", the Radix Select renders the matching
    // SelectItem content, which is the uppercase label "PDF"
    expect(screen.getByText("PDF")).toBeInTheDocument();
  });

  it("calls onSearchChange with empty string when clearing", () => {
    render(
      <DocumentFilters
        search="test"
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const input = screen.getByPlaceholderText("Search documents...");
    fireEvent.change(input, { target: { value: "" } });
    expect(onSearchChange).toHaveBeenCalledWith("");
  });

  it("renders the select trigger element", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    // The select trigger should be a button with combobox role
    const trigger = screen.getByRole("combobox");
    expect(trigger).toBeInTheDocument();
  });

  it("renders search and select side by side in flex container", () => {
    const { container } = render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const wrapper = container.firstElementChild;
    expect(wrapper?.className).toContain("flex");
  });

  it("calls onSearchChange multiple times as user types", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const input = screen.getByPlaceholderText("Search documents...");
    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.change(input, { target: { value: "ab" } });
    fireEvent.change(input, { target: { value: "abc" } });
    expect(onSearchChange).toHaveBeenCalledTimes(3);
  });

  it("search input has correct type attribute", () => {
    render(
      <DocumentFilters
        search=""
        onSearchChange={onSearchChange}
        fileExtension="all"
        onFileExtensionChange={onFileExtensionChange}
      />,
    );
    const input = screen.getByPlaceholderText("Search documents...");
    // Default input type should exist
    expect(input.tagName).toBe("INPUT");
  });
});
