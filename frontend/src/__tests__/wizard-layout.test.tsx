import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { WizardLayout } from "@/components/case-setup/wizard-layout";

describe("WizardLayout", () => {
  const defaultProps = {
    currentStep: 0,
    onBack: vi.fn(),
    onNext: vi.fn(),
    canGoNext: true,
    isLastStep: false,
    children: <div>Step Content</div>,
  };

  it("renders step labels", () => {
    render(<WizardLayout {...defaultProps} />);
    expect(screen.getByText("Upload")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Claims")).toBeInTheDocument();
    expect(screen.getByText("Parties & Terms")).toBeInTheDocument();
    expect(screen.getByText("Confirm")).toBeInTheDocument();
  });

  it("renders children", () => {
    render(<WizardLayout {...defaultProps} />);
    expect(screen.getByText("Step Content")).toBeInTheDocument();
  });

  it("renders Back and Next buttons", () => {
    render(<WizardLayout {...defaultProps} />);
    expect(screen.getByText("Back")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("disables Back button on first step", () => {
    render(<WizardLayout {...defaultProps} currentStep={0} />);
    expect(screen.getByText("Back")).toBeDisabled();
  });

  it("enables Back button on non-first step", () => {
    render(<WizardLayout {...defaultProps} currentStep={2} />);
    expect(screen.getByText("Back")).not.toBeDisabled();
  });

  it("disables Next when canGoNext is false", () => {
    render(<WizardLayout {...defaultProps} canGoNext={false} />);
    expect(screen.getByText("Next")).toBeDisabled();
  });

  it("shows 'Confirm & Save' on last step", () => {
    render(<WizardLayout {...defaultProps} isLastStep={true} />);
    expect(screen.getByText("Confirm & Save")).toBeInTheDocument();
    expect(screen.queryByText("Next")).not.toBeInTheDocument();
  });

  it("calls onNext when Next is clicked", () => {
    const onNext = vi.fn();
    render(<WizardLayout {...defaultProps} onNext={onNext} />);
    fireEvent.click(screen.getByText("Next"));
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("calls onBack when Back is clicked", () => {
    const onBack = vi.fn();
    render(<WizardLayout {...defaultProps} currentStep={2} onBack={onBack} />);
    fireEvent.click(screen.getByText("Back"));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
