import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";

const mockNavigate = vi.fn();
const mockLogin = vi.fn();
const mockSetTokens = vi.fn();
const mockLogout = vi.fn();
const mockApiClient = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  useNavigate: () => mockNavigate,
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ login: mockLogin }),
    {
      getState: () => ({
        setTokens: mockSetTokens,
        logout: mockLogout,
      }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: (...args: unknown[]) => mockApiClient(...args),
}));

// Import after mocks
import { Route } from "@/routes/login";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password inputs", () => {
    render(<Component />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders NEXUS title", () => {
    render(<Component />);
    expect(screen.getByText("NEXUS")).toBeInTheDocument();
  });

  it("renders sign in button", () => {
    render(<Component />);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows validation error for invalid email on submit", async () => {
    render(<Component />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "not-an-email" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "password123" },
      });
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
    });

    await waitFor(() => {
      expect(screen.getByText("Invalid email address")).toBeInTheDocument();
    });
  });

  it("shows validation error for empty password", async () => {
    render(<Component />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "test@example.com" },
      });
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
    });

    await waitFor(() => {
      expect(screen.getByText("Password is required")).toBeInTheDocument();
    });
  });

  it("calls API on valid form submission", async () => {
    mockApiClient
      .mockResolvedValueOnce({
        access_token: "at-123",
        refresh_token: "rt-456",
        token_type: "bearer",
      })
      .mockResolvedValueOnce({
        id: "user-1",
        email: "test@example.com",
        full_name: "Test User",
        role: "admin",
        is_active: true,
        created_at: "2024-01-01",
      });

    render(<Component />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(mockApiClient).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/auth/login",
          method: "POST",
        }),
      );
    });
  });

  it("shows error alert on failed login", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Invalid credentials"));

    render(<Component />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });

  it("toggles password visibility", () => {
    render(<Component />);

    const passwordInput = screen.getByLabelText("Password");
    expect(passwordInput).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByLabelText("Show password"));
    expect(passwordInput).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByLabelText("Hide password"));
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("shows 'Signing in...' when submitting", async () => {
    mockApiClient.mockImplementation(() => new Promise(() => {}));

    render(<Component />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByText("Signing in...")).toBeInTheDocument();
    });
  });

  it("renders legal platform description", () => {
    render(<Component />);
    expect(
      screen.getByText("Legal Document Intelligence Platform"),
    ).toBeInTheDocument();
  });
});
