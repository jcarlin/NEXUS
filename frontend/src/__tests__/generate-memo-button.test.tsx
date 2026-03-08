import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---- Mocks ---- //

const mockApiClient = vi.fn();
vi.mock("@/api/client", () => ({
  apiClient: (...args: unknown[]) => mockApiClient(...args),
}));

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({ accessToken: "test-token" }),
  },
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

vi.mock("@/hooks/use-notifications", () => ({
  useNotifications: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
  }),
}));

vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }: { children: string }) => <pre>{children}</pre>,
}));

vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  oneDark: {},
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
    <a href={props.to}>{children}</a>
  ),
}));

import { GenerateMemoButton } from "@/components/chat/generate-memo-button";
import { MessageActions } from "@/components/chat/message-actions";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("GenerateMemoButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders memo button with threadId", () => {
    render(<GenerateMemoButton threadId="t-123" />, { wrapper: createWrapper() });
    expect(screen.getByRole("button", { name: /memo/i })).toBeInTheDocument();
  });

  it("shows loading state during generation", async () => {
    const user = userEvent.setup();
    // Never-resolving promise to keep pending state
    mockApiClient.mockReturnValue(new Promise(() => {}));

    render(<GenerateMemoButton threadId="t-123" />, { wrapper: createWrapper() });

    const button = screen.getByRole("button", { name: /memo/i });
    await user.click(button);

    await waitFor(() => {
      expect(button).toBeDisabled();
    });
  });

  it("calls API with correct params", async () => {
    const user = userEvent.setup();
    const mockMemo = {
      id: "memo-1",
      matter_id: "matter-1",
      thread_id: "t-123",
      title: "Test Memo",
      sections: [{ heading: "Summary", content: "Test content", citations: [] }],
      format: "markdown",
      created_by: "user-1",
      created_at: "2026-03-08T00:00:00Z",
    };
    mockApiClient.mockResolvedValue(mockMemo);

    render(<GenerateMemoButton threadId="t-123" />, { wrapper: createWrapper() });

    await user.click(screen.getByRole("button", { name: /memo/i }));

    await waitFor(() => {
      expect(mockApiClient).toHaveBeenCalledWith({
        url: "/api/v1/memos",
        method: "POST",
        data: { thread_id: "t-123", matter_id: "matter-1" },
      });
    });
  });
});

describe("MessageActions memo integration", () => {
  it("does not render memo button without threadId", () => {
    render(<MessageActions content="test" />, { wrapper: createWrapper() });
    expect(screen.queryByRole("button", { name: /memo/i })).not.toBeInTheDocument();
  });

  it("renders memo button when threadId is provided", () => {
    render(<MessageActions content="test" threadId="t-123" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByRole("button", { name: /memo/i })).toBeInTheDocument();
  });
});
