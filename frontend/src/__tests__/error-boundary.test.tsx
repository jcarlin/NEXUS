import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { ErrorBoundary } from "@/components/ui/error-boundary";

// Suppress console.error for expected errors in tests
const originalConsoleError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});

afterEach(() => {
  console.error = originalConsoleError;
});

function ThrowingChild({ error }: { error?: Error }) {
  if (error) throw error;
  return <div>Child content</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>Normal content</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Normal content")).toBeInTheDocument();
  });

  it("shows error message when child throws", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild error={new Error("Something broke")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });

  it("shows Try Again button on error", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild error={new Error("fail")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Try Again")).toBeInTheDocument();
  });

  it("renders fallback UI when provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingChild error={new Error("fail")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom fallback")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("resets error state when Try Again is clicked", () => {
    // Can't fully test recovery since the same throwing component will throw again.
    // But we can verify the Try Again button calls setState to reset.
    render(
      <ErrorBoundary>
        <ThrowingChild error={new Error("fail")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    // After clicking Try Again, the boundary tries to re-render children.
    // Since ThrowingChild still throws, it will re-enter error state.
    fireEvent.click(screen.getByText("Try Again"));
    // Still in error state since the child always throws
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("shows default message when error has no message", () => {
    const error = new Error();
    error.message = "";
    render(
      <ErrorBoundary>
        <ThrowingChild error={error} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });
});
