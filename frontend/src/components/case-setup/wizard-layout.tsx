import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Check, Upload, Loader2, Scale, Users, ClipboardCheck } from "lucide-react";

const STEPS = [
  { label: "Upload", icon: Upload },
  { label: "Processing", icon: Loader2 },
  { label: "Claims", icon: Scale },
  { label: "Parties & Terms", icon: Users },
  { label: "Confirm", icon: ClipboardCheck },
] as const;

interface WizardLayoutProps {
  currentStep: number;
  onBack: () => void;
  onNext: () => void;
  canGoNext: boolean;
  isLastStep: boolean;
  children: React.ReactNode;
}

export function WizardLayout({
  currentStep,
  onBack,
  onNext,
  canGoNext,
  isLastStep,
  children,
}: WizardLayoutProps) {
  return (
    <div className="space-y-8">
      {/* Step indicator */}
      <nav className="flex items-center justify-center gap-2">
        {STEPS.map((step, index) => {
          const Icon = step.icon;
          const isComplete = index < currentStep;
          const isCurrent = index === currentStep;

          return (
            <div key={step.label} className="flex items-center">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-full border-2 transition-colors",
                    isComplete && "border-primary bg-primary text-primary-foreground",
                    isCurrent && "border-primary text-primary",
                    !isComplete && !isCurrent && "border-muted-foreground/30 text-muted-foreground/50",
                  )}
                >
                  {isComplete ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Icon className="h-4 w-4" />
                  )}
                </div>
                <span
                  className={cn(
                    "text-[11px] font-medium",
                    isCurrent ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mb-4 mx-1 h-0.5 w-12",
                    index < currentStep ? "bg-primary" : "bg-muted-foreground/20",
                  )}
                />
              )}
            </div>
          );
        })}
      </nav>

      {/* Step content */}
      <div className="mx-auto max-w-3xl">{children}</div>

      {/* Navigation buttons */}
      <div className="mx-auto flex max-w-3xl justify-between">
        <Button
          variant="outline"
          onClick={onBack}
          disabled={currentStep === 0}
        >
          Back
        </Button>
        <Button onClick={onNext} disabled={!canGoNext}>
          {isLastStep ? "Confirm & Save" : "Next"}
        </Button>
      </div>
    </div>
  );
}
