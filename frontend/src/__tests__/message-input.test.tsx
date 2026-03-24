import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageInput } from "@/components/chat/message-input";

// Mock the apiClient to return a model response
vi.mock("@/api/client", () => ({
  apiClient: vi.fn().mockResolvedValue({
    tier: "query",
    model: "gemini-2.0-flash",
    provider_type: "gemini",
  }),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("MessageInput", () => {
  const onSend = vi.fn();
  const onStop = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders textarea with correct placeholder", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    expect(
      screen.getByPlaceholderText("Ask a question about the investigation..."),
    ).toBeInTheDocument();
  });

  it("send button is disabled when textarea is empty", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();
  });

  it("send button is enabled when textarea has text", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeEnabled();
  });

  it("calls onSend with trimmed text on button click", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "  Hello World  " } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    fireEvent.click(sendButton);
    expect(onSend).toHaveBeenCalledWith("Hello World");
  });

  it("calls onSend on Enter key (not Shift+Enter)", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Enter test" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("Enter test");
  });

  it("does NOT call onSend on Shift+Enter", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("clears textarea after sending", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(textarea.value).toBe("");
  });

  it("shows Stop button when isStreaming=true", () => {
    render(<MessageInput onSend={onSend} onStop={onStop} isStreaming />, {
      wrapper: createWrapper(),
    });
    expect(
      screen.getByRole("button", { name: "Stop generating" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  });

  it("Stop button calls onStop", () => {
    render(<MessageInput onSend={onSend} onStop={onStop} isStreaming />, {
      wrapper: createWrapper(),
    });
    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("textarea is disabled when disabled=true", () => {
    render(<MessageInput onSend={onSend} disabled />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    expect(textarea).toBeDisabled();
  });

  it("does not call onSend when disabled even with text", () => {
    render(<MessageInput onSend={onSend} disabled />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows hint text about Enter/Shift+Enter", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    expect(screen.getByText(/Enter to send/)).toBeInTheDocument();
    expect(screen.getByText(/Shift\+Enter for new line/)).toBeInTheDocument();
  });

  it("does not send when textarea contains only whitespace", () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "   " } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();
  });

  it("renders model badge when active model is fetched", async () => {
    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const badge = await screen.findByText("gemini-2.0-flash");
    expect(badge).toBeInTheDocument();
  });

  it("renders with border-t by default", () => {
    const { container } = render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).toContain("border-t");
  });

  it("renders without border-t when variant is standalone", () => {
    const { container } = render(<MessageInput onSend={onSend} variant="standalone" />, {
      wrapper: createWrapper(),
    });
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).not.toContain("border-t");
  });

  describe("hero variant", () => {
    it("renders textarea with rows=4", () => {
      render(<MessageInput onSend={onSend} variant="hero" />, { wrapper: createWrapper() });
      const textarea = screen.getByPlaceholderText("Ask a question about the investigation...");
      expect(textarea).toHaveAttribute("rows", "4");
    });

    it("does not show border-t", () => {
      const { container } = render(<MessageInput onSend={onSend} variant="hero" />, {
        wrapper: createWrapper(),
      });
      const outer = container.firstElementChild as HTMLElement;
      expect(outer.className).not.toContain("border-t");
    });

    it("shows model badge inside container", async () => {
      render(<MessageInput onSend={onSend} variant="hero" />, { wrapper: createWrapper() });
      const badge = await screen.findByText("gemini-2.0-flash");
      expect(badge).toBeInTheDocument();
    });

    it("does not show Enter hint text", () => {
      render(<MessageInput onSend={onSend} variant="hero" />, { wrapper: createWrapper() });
      expect(screen.queryByText(/Enter to send/)).not.toBeInTheDocument();
    });
  });

  it("does not render badge when fetch fails", async () => {
    const { apiClient } = await import("@/api/client");
    vi.mocked(apiClient).mockRejectedValueOnce(new Error("Network error"));

    render(<MessageInput onSend={onSend} />, { wrapper: createWrapper() });
    // Badge should not appear — query fails silently
    expect(screen.queryByText("gemini-2.0-flash")).not.toBeInTheDocument();
  });
});
