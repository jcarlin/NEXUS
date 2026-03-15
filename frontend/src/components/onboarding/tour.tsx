import { useCallback, useEffect, useState } from "react";
import Joyride, { type CallBackProps, STATUS } from "react-joyride";
import { useOnboarding } from "@/hooks/use-onboarding";
import { dashboardSteps } from "./steps";

export function OnboardingTour() {
  const { run, completed, currentStep, startTour, completeTour, setCurrentStep } =
    useOnboarding();
  const [targetsReady, setTargetsReady] = useState(false);

  // Check that all step target elements exist in the DOM
  const checkTargets = useCallback(() => {
    return dashboardSteps.every(
      (step) =>
        typeof step.target === "string" &&
        document.querySelector(step.target) !== null,
    );
  }, []);

  // Wait for all tour targets to mount before enabling the tour
  useEffect(() => {
    if (completed || targetsReady) return;

    if (checkTargets()) {
      setTargetsReady(true);
      return;
    }

    const interval = setInterval(() => {
      if (checkTargets()) {
        setTargetsReady(true);
        clearInterval(interval);
      }
    }, 500);

    // Stop polling after 10 s — targets never appeared (wrong page, etc.)
    const timeout = setTimeout(() => clearInterval(interval), 10_000);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [completed, targetsReady, checkTargets]);

  // Auto-start tour on first visit once targets are ready
  useEffect(() => {
    if (targetsReady && !completed && !run) {
      startTour();
    }
  }, [targetsReady]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleCallback(data: CallBackProps) {
    const { status, index } = data;

    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      completeTour();
      return;
    }

    setCurrentStep(index);
  }

  return (
    <Joyride
      steps={dashboardSteps}
      run={run && targetsReady}
      stepIndex={currentStep}
      continuous
      showSkipButton
      showProgress
      disableScrolling
      spotlightClicks
      callback={handleCallback}
      styles={{
        options: {
          arrowColor: "var(--color-card)",
          backgroundColor: "var(--color-card)",
          overlayColor: "rgba(0, 0, 0, 0.5)",
          primaryColor: "var(--color-primary)",
          textColor: "var(--color-card-foreground)",
          zIndex: 10000,
        },
        tooltipContainer: {
          textAlign: "left" as const,
        },
        buttonNext: {
          backgroundColor: "var(--color-primary)",
          color: "var(--color-primary-foreground)",
          borderRadius: "6px",
          fontSize: "14px",
          padding: "8px 16px",
        },
        buttonBack: {
          color: "var(--color-muted-foreground)",
          fontSize: "14px",
          marginRight: "8px",
        },
        buttonSkip: {
          color: "var(--color-muted-foreground)",
          fontSize: "13px",
        },
        tooltip: {
          borderRadius: "12px",
          padding: "20px",
        },
      }}
      locale={{
        back: "Back",
        close: "Close",
        last: "Done",
        next: "Next",
        skip: "Skip tour",
      }}
    />
  );
}
