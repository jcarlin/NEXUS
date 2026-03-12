import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockNavigate = vi.fn();
const mockLogout = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({
        user: { email: "admin@test.com", full_name: "Admin User", role: "admin" },
        logout: mockLogout,
      }),
    {
      getState: () => ({
        user: { email: "admin@test.com", full_name: "Admin User", role: "admin" },
        logout: mockLogout,
      }),
    },
  ),
}));

vi.mock("@/components/layout/matter-selector", () => ({
  MatterSelector: () => <div data-testid="matter-selector">Matter Selector</div>,
}));

vi.mock("@/components/datasets/dataset-selector", () => ({
  DatasetSelector: () => <div data-testid="dataset-selector">Dataset Selector</div>,
}));

import { Header } from "@/components/layout/header";

describe("Header", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders matter selector", () => {
    render(<Header />);
    expect(screen.getByTestId("matter-selector")).toBeInTheDocument();
  });

  it("renders dataset selector", () => {
    render(<Header />);
    expect(screen.getByTestId("dataset-selector")).toBeInTheDocument();
  });

  it("renders keyboard shortcut hint", () => {
    render(<Header />);
    expect(screen.getByText("Ctrl+K")).toBeInTheDocument();
  });

  it("renders user avatar with initials", () => {
    render(<Header />);
    expect(screen.getByText("AU")).toBeInTheDocument();
  });
});
