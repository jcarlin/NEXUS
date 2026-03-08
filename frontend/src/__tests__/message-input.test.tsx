import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageInput } from "@/components/chat/message-input";

describe("MessageInput", () => {
  const onSend = vi.fn();
  const onStop = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders textarea with correct placeholder", () => {
    render(<MessageInput onSend={onSend} />);
    expect(
      screen.getByPlaceholderText("Ask a question about the investigation..."),
    ).toBeInTheDocument();
  });

  it("send button is disabled when textarea is empty", () => {
    render(<MessageInput onSend={onSend} />);
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();
  });

  it("send button is enabled when textarea has text", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeEnabled();
  });

  it("calls onSend with trimmed text on button click", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "  Hello World  " } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    fireEvent.click(sendButton);
    expect(onSend).toHaveBeenCalledWith("Hello World");
  });

  it("calls onSend on Enter key (not Shift+Enter)", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Enter test" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("Enter test");
  });

  it("does NOT call onSend on Shift+Enter", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("clears textarea after sending", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(textarea.value).toBe("");
  });

  it("shows Stop button when isStreaming=true", () => {
    render(<MessageInput onSend={onSend} onStop={onStop} isStreaming />);
    expect(
      screen.getByRole("button", { name: "Stop generating" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  });

  it("Stop button calls onStop", () => {
    render(<MessageInput onSend={onSend} onStop={onStop} isStreaming />);
    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("textarea is disabled when disabled=true", () => {
    render(<MessageInput onSend={onSend} disabled />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    expect(textarea).toBeDisabled();
  });

  it("does not call onSend when disabled even with text", () => {
    render(<MessageInput onSend={onSend} disabled />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows hint text about Enter/Shift+Enter", () => {
    render(<MessageInput onSend={onSend} />);
    expect(screen.getByText(/Enter to send/)).toBeInTheDocument();
    expect(screen.getByText(/Shift\+Enter for new line/)).toBeInTheDocument();
  });

  it("does not send when textarea contains only whitespace", () => {
    render(<MessageInput onSend={onSend} />);
    const textarea = screen.getByPlaceholderText(
      "Ask a question about the investigation...",
    );
    fireEvent.change(textarea, { target: { value: "   " } });
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();
  });
});
