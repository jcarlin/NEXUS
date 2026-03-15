import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import React from "react";
import { useOnboarding } from "@/hooks/use-onboarding";

// Mock react-joyride to capture props
const mockJoyride = vi.fn(() => null);
vi.mock("react-joyride", () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    mockJoyride(props);
    return null;
  },
  STATUS: {
    FINISHED: "finished",
    SKIPPED: "skipped",
  },
}));

// Import after mocks are set up
import { OnboardingTour } from "@/components/onboarding/tour";

/** Create DOM elements that match tour step selectors. */
function mountTourTargets() {
  const ids = ["sidebar-nav", "matter-selector", "stat-cards", "recent-activity"];
  for (const id of ids) {
    const el = document.createElement("div");
    el.setAttribute("data-tour", id);
    document.body.appendChild(el);
  }
}

function removeTourTargets() {
  document.querySelectorAll("[data-tour]").forEach((el) => el.remove());
}

describe("OnboardingTour", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    useOnboarding.setState({
      completed: false,
      currentStep: 0,
      run: false,
    });
    mountTourTargets();
  });

  afterEach(() => {
    removeTourTargets();
    vi.useRealTimers();
  });

  it("renders Joyride with dashboard steps", () => {
    render(<OnboardingTour />);
    expect(mockJoyride).toHaveBeenCalled();
    const props = mockJoyride.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(props).toBeDefined();
    expect(Array.isArray(props.steps)).toBe(true);
    expect((props.steps as unknown[]).length).toBeGreaterThan(0);
  });

  it("auto-starts tour when targets are ready", () => {
    render(<OnboardingTour />);

    // Targets are already in the DOM, so tour should auto-start
    const state = useOnboarding.getState();
    expect(state.run).toBe(true);
  });

  it("waits for targets before starting tour", () => {
    removeTourTargets();
    render(<OnboardingTour />);

    // No targets — tour should NOT be running
    expect(useOnboarding.getState().run).toBe(false);

    // Add targets and advance the polling timer
    mountTourTargets();
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(useOnboarding.getState().run).toBe(true);
  });

  it("does not start tour if already completed", () => {
    useOnboarding.setState({ completed: true });
    render(<OnboardingTour />);

    expect(useOnboarding.getState().run).toBe(false);
  });

  it("calls completeTour on FINISHED status", () => {
    render(<OnboardingTour />);
    const props = mockJoyride.mock.calls[0]?.[0] as Record<string, unknown>;
    const callback = props.callback as (data: Record<string, unknown>) => void;

    act(() => {
      callback({ status: "finished", index: 3, type: "tour:end", action: "next" });
    });

    const state = useOnboarding.getState();
    expect(state.completed).toBe(true);
    expect(state.run).toBe(false);
  });

  it("passes run=false to Joyride when targets are missing", () => {
    removeTourTargets();
    render(<OnboardingTour />);

    const props = mockJoyride.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(props.run).toBe(false);
  });
});
