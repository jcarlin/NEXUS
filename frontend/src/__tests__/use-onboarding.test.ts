import { describe, it, expect, beforeEach } from "vitest";
import { useOnboarding } from "@/hooks/use-onboarding";

describe("useOnboarding", () => {
  beforeEach(() => {
    useOnboarding.setState({
      completed: false,
      currentStep: 0,
      run: false,
    });
    localStorage.removeItem("nexus-onboarding-v1");
  });

  it("has correct initial state", () => {
    const state = useOnboarding.getState();
    expect(state.completed).toBe(false);
    expect(state.currentStep).toBe(0);
    expect(state.run).toBe(false);
  });

  it("startTour sets run to true and resets step", () => {
    useOnboarding.getState().setCurrentStep(3);
    useOnboarding.getState().startTour();
    const state = useOnboarding.getState();
    expect(state.run).toBe(true);
    expect(state.currentStep).toBe(0);
  });

  it("completeTour marks completed and stops run", () => {
    useOnboarding.getState().startTour();
    useOnboarding.getState().completeTour();
    const state = useOnboarding.getState();
    expect(state.completed).toBe(true);
    expect(state.run).toBe(false);
    expect(state.currentStep).toBe(0);
  });

  it("resetTour clears completed state", () => {
    useOnboarding.getState().completeTour();
    expect(useOnboarding.getState().completed).toBe(true);

    useOnboarding.getState().resetTour();
    const state = useOnboarding.getState();
    expect(state.completed).toBe(false);
    expect(state.run).toBe(false);
    expect(state.currentStep).toBe(0);
  });
});
