import { useEffect } from "react";
import Joyride, { type CallBackProps, STATUS } from "react-joyride";
import { useOnboarding } from "@/hooks/use-onboarding";
import { dashboardSteps } from "./steps";

export function OnboardingTour() {
  const { run, completed, currentStep, startTour, completeTour, setCurrentStep } =
    useOnboarding();

  // Auto-start tour on first visit
  useEffect(() => {
    if (!completed && !run) {
      startTour();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
      run={run}
      stepIndex={currentStep}
      continuous
      showSkipButton
      showProgress
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
