import { describe, it, expect, vi, beforeEach } from "vitest";
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

describe("OnboardingTour", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOnboarding.setState({
      completed: false,
      currentStep: 0,
      run: false,
    });
  });

  it("renders Joyride with dashboard steps", () => {
    render(<OnboardingTour />);
    expect(mockJoyride).toHaveBeenCalled();
    const props = mockJoyride.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(props).toBeDefined();
    expect(Array.isArray(props.steps)).toBe(true);
    expect((props.steps as unknown[]).length).toBeGreaterThan(0);
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
});
