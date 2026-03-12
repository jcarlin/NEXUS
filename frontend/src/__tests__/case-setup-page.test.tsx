import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1" }),
    {
      getState: () => ({ matterId: "matter-1" }),
    },
  ),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/hooks/use-feature-flags", () => ({
  useFeatureFlag: () => true,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

vi.mock("@/components/ui/feature-disabled-banner", () => ({
  FeatureDisabledBanner: ({ featureName }: { featureName: string }) => (
    <div data-testid="feature-disabled">{featureName}</div>
  ),
}));

vi.mock("@/components/case-setup/wizard-layout", () => ({
  WizardLayout: ({
    children,
    onBack,
    onNext,
    canGoNext,
    isLastStep,
  }: {
    children: React.ReactNode;
    onBack: () => void;
    onNext: () => void;
    canGoNext: boolean;
    isLastStep: boolean;
  }) => (
    <div data-testid="wizard-layout">
      {children}
      <button onClick={onBack} disabled={false}>Back</button>
      <button onClick={onNext} disabled={!canGoNext}>
        {isLastStep ? "Confirm & Save" : "Next"}
      </button>
    </div>
  ),
}));

vi.mock("@/components/case-setup/step-upload", () => ({
  StepUpload: () => <div data-testid="step-upload">Upload Step</div>,
}));

vi.mock("@/components/case-setup/step-processing", () => ({
  StepProcessing: () => <div data-testid="step-processing">Processing Step</div>,
}));

vi.mock("@/components/case-setup/step-claims", () => ({
  StepClaims: () => <div data-testid="step-claims">Claims Step</div>,
}));

vi.mock("@/components/case-setup/step-parties-terms", () => ({
  StepPartiesTerms: () => <div data-testid="step-parties-terms">Parties Step</div>,
}));

vi.mock("@/components/case-setup/step-confirm", () => ({
  StepConfirm: () => <div data-testid="step-confirm">Confirm Step</div>,
}));

vi.mock("@/components/case-setup/context-summary", () => ({
  ContextSummary: ({ onRerun }: { onRerun: () => void }) => (
    <div data-testid="context-summary">
      <button onClick={onRerun}>Re-run</button>
    </div>
  ),
}));

import { Route } from "@/routes/case-setup";

const Component = (Route as unknown as { component: React.ComponentType }).component;

describe("CaseSetupPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
    });
  });

  it("shows loading state when context is loading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true });
    render(<Component />);
    expect(screen.getByText("Loading case context...")).toBeInTheDocument();
  });

  it("renders Case Setup heading", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByText("Case Setup")).toBeInTheDocument();
  });

  it("shows ContextSummary when context is confirmed", () => {
    mockUseQuery.mockReturnValue({
      data: { status: "confirmed", claims: [], parties: [] },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByTestId("context-summary")).toBeInTheDocument();
  });

  it("shows wizard when no existing context", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByTestId("wizard-layout")).toBeInTheDocument();
  });

  it("starts on upload step", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(screen.getByTestId("step-upload")).toBeInTheDocument();
  });

  it("shows re-run button for confirmed context", () => {
    mockUseQuery.mockReturnValue({
      data: { status: "confirmed" },
      isLoading: false,
    });
    render(<Component />);
    expect(screen.getByText("Re-run")).toBeInTheDocument();
  });

  it("switches to wizard when re-run is clicked", () => {
    mockUseQuery.mockReturnValue({
      data: { status: "confirmed" },
      isLoading: false,
    });
    render(<Component />);
    fireEvent.click(screen.getByText("Re-run"));
    expect(screen.getByTestId("wizard-layout")).toBeInTheDocument();
  });

  it("renders description text", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
    render(<Component />);
    expect(
      screen.getByText("Configure case context: upload documents, define claims, parties, and terms."),
    ).toBeInTheDocument();
  });
});
