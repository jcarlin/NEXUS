import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ClarificationPrompt } from "@/components/chat/clarification-prompt";

describe("ClarificationPrompt", () => {
  const onSubmit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders question text", () => {
    render(<ClarificationPrompt question="Which Smith?" onSubmit={onSubmit} />);
    expect(screen.getByText("Which Smith?")).toBeInTheDocument();
  });

  it("calls onSubmit with answer on button click", () => {
    render(<ClarificationPrompt question="Which Smith?" onSubmit={onSubmit} />);
    const textarea = screen.getByPlaceholderText("Type your answer...");
    fireEvent.change(textarea, { target: { value: "John Smith" } });
    const submitButton = screen.getByRole("button");
    fireEvent.click(submitButton);
    expect(onSubmit).toHaveBeenCalledWith("John Smith");
  });

  it("calls onSubmit on Enter key", () => {
    render(<ClarificationPrompt question="Which Smith?" onSubmit={onSubmit} />);
    const textarea = screen.getByPlaceholderText("Type your answer...");
    fireEvent.change(textarea, { target: { value: "John Smith" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSubmit).toHaveBeenCalledWith("John Smith");
  });

  it("does not submit on Shift+Enter", () => {
    render(<ClarificationPrompt question="Which Smith?" onSubmit={onSubmit} />);
    const textarea = screen.getByPlaceholderText("Type your answer...");
    fireEvent.change(textarea, { target: { value: "John Smith" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables input when isResuming", () => {
    render(
      <ClarificationPrompt
        question="Which Smith?"
        onSubmit={onSubmit}
        isResuming
      />,
    );
    const textarea = screen.getByPlaceholderText("Type your answer...");
    expect(textarea).toBeDisabled();
    const submitButton = screen.getByRole("button");
    expect(submitButton).toBeDisabled();
  });

  it("does not submit empty answer", () => {
    render(<ClarificationPrompt question="Which Smith?" onSubmit={onSubmit} />);
    const submitButton = screen.getByRole("button");
    fireEvent.click(submitButton);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
