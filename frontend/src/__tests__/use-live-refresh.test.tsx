import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveRefreshProvider, useLiveRefresh } from "@/hooks/use-live-refresh";

function TestConsumer() {
  const { isLive, toggleLive } = useLiveRefresh();
  return (
    <div>
      <span data-testid="status">{isLive ? "live" : "paused"}</span>
      <button onClick={toggleLive}>toggle</button>
    </div>
  );
}

describe("useLiveRefresh", () => {
  it("defaults to isLive=true with provider", () => {
    render(
      <LiveRefreshProvider>
        <TestConsumer />
      </LiveRefreshProvider>,
    );
    expect(screen.getByTestId("status")).toHaveTextContent("live");
  });

  it("toggleLive flips state", () => {
    render(
      <LiveRefreshProvider>
        <TestConsumer />
      </LiveRefreshProvider>,
    );
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("status")).toHaveTextContent("paused");
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("status")).toHaveTextContent("live");
  });

  it("returns isLive=true when no provider (graceful degradation)", () => {
    render(<TestConsumer />);
    expect(screen.getByTestId("status")).toHaveTextContent("live");
  });
});
