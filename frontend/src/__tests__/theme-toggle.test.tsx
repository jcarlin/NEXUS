import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { ThemeToggle } from "@/components/layout/theme-toggle";

const mockSetTheme = vi.fn();
const mockToggle = vi.fn();

vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({
    theme: "system",
    resolved: "dark",
    setTheme: mockSetTheme,
    toggle: mockToggle,
  }),
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the toggle button", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
  });

  it("opens dropdown with three options on click", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: /toggle theme/i }));

    expect(screen.getByText("Light")).toBeInTheDocument();
    expect(screen.getByText("Dark")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
  });

  it("calls setTheme with 'light' when Light is selected", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: /toggle theme/i }));
    await user.click(screen.getByText("Light"));

    expect(mockSetTheme).toHaveBeenCalledWith("light");
  });

  it("calls setTheme with 'dark' when Dark is selected", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: /toggle theme/i }));
    await user.click(screen.getByText("Dark"));

    expect(mockSetTheme).toHaveBeenCalledWith("dark");
  });

  it("calls setTheme with 'system' when System is selected", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: /toggle theme/i }));
    await user.click(screen.getByText("System"));

    expect(mockSetTheme).toHaveBeenCalledWith("system");
  });
});
