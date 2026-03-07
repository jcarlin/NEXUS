import { useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { WizardLayout } from "@/components/case-setup/wizard-layout";
import { StepUpload } from "@/components/case-setup/step-upload";
import { StepProcessing } from "@/components/case-setup/step-processing";
import { StepClaims } from "@/components/case-setup/step-claims";
import { StepPartiesTerms } from "@/components/case-setup/step-parties-terms";
import { StepConfirm } from "@/components/case-setup/step-confirm";

export const Route = createFileRoute("/case-setup")({
  component: CaseSetupPage,
});

interface Claim {
  id: string;
  claim_number: number;
  claim_label: string;
  claim_text: string;
}

type PartyRole = "plaintiff" | "defendant" | "third_party" | "witness" | "counsel";

interface Party {
  id: string;
  name: string;
  role: PartyRole | "";
}

interface DefinedTerm {
  id: string;
  term: string;
  definition: string;
}

let nextId = 1;
function genId() {
  return String(nextId++);
}

function CaseSetupPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [step, setStep] = useState(0);
  const [uploaded, setUploaded] = useState(false);
  // Stored for future use (e.g. direct context polling)
  const [, setCaseContextId] = useState<string | null>(null);
  const [processingDone, setProcessingDone] = useState(false);

  const [claims, setClaims] = useState<Claim[]>([
    { id: genId(), claim_number: 1, claim_label: "", claim_text: "" },
  ]);
  const [parties, setParties] = useState<Party[]>([]);
  const [terms, setTerms] = useState<DefinedTerm[]>([]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiClient<void>({
        url: `/api/v1/cases/${matterId}/context`,
        method: "PATCH",
        data: {
          status: "confirmed",
          claims: claims
            .filter((c) => c.claim_text.trim())
            .map((c) => ({
              claim_number: c.claim_number,
              claim_label: c.claim_label,
              claim_text: c.claim_text,
            })),
          parties: parties
            .filter((p) => p.name.trim() && p.role)
            .map((p) => ({ name: p.name, role: p.role })),
          defined_terms: terms
            .filter((t) => t.term.trim())
            .map((t) => ({ term: t.term, definition: t.definition })),
        },
      }),
  });

  const handleProcessingComplete = useCallback(() => {
    setProcessingDone(true);
  }, []);

  const canGoNext = (() => {
    switch (step) {
      case 0: return uploaded;
      case 1: return processingDone;
      case 2: return true;
      case 3: return true;
      case 4: return !saveMutation.isPending;
      default: return false;
    }
  })();

  function handleNext() {
    if (step === 4) {
      saveMutation.mutate();
      return;
    }
    setStep((s) => Math.min(s + 1, 4));
  }

  function handleBack() {
    setStep((s) => Math.max(s - 1, 0));
  }

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Case Setup</h1>
        <p className="text-muted-foreground">
          Configure case context: upload documents, define claims, parties, and terms.
        </p>
      </div>

      <WizardLayout
        currentStep={step}
        onBack={handleBack}
        onNext={handleNext}
        canGoNext={canGoNext}
        isLastStep={step === 4}
      >
        {step === 0 && (
          <StepUpload
            onUploadComplete={(result) => {
              setCaseContextId(result.case_context_id);
              setUploaded(true);
              setStep(1);
            }}
          />
        )}
        {step === 1 && (
          <StepProcessing onProcessingComplete={handleProcessingComplete} />
        )}
        {step === 2 && (
          <StepClaims
            claims={claims}
            onAdd={() =>
              setClaims((prev) => [
                ...prev,
                {
                  id: genId(),
                  claim_number: prev.length + 1,
                  claim_label: "",
                  claim_text: "",
                },
              ])
            }
            onRemove={(id) =>
              setClaims((prev) =>
                prev
                  .filter((c) => c.id !== id)
                  .map((c, i) => ({ ...c, claim_number: i + 1 })),
              )
            }
            onUpdate={(id, field, value) =>
              setClaims((prev) =>
                prev.map((c) => (c.id === id ? { ...c, [field]: value } : c)),
              )
            }
          />
        )}
        {step === 3 && (
          <StepPartiesTerms
            parties={parties}
            onAddParty={() =>
              setParties((prev) => [
                ...prev,
                { id: genId(), name: "", role: "" as Party["role"] },
              ])
            }
            onRemoveParty={(id) =>
              setParties((prev) => prev.filter((p) => p.id !== id))
            }
            onUpdateParty={(id, field, value) =>
              setParties((prev) =>
                prev.map((p) =>
                  p.id === id ? { ...p, [field]: value } : p,
                ),
              )
            }
            terms={terms}
            onAddTerm={() =>
              setTerms((prev) => [
                ...prev,
                { id: genId(), term: "", definition: "" },
              ])
            }
            onRemoveTerm={(id) =>
              setTerms((prev) => prev.filter((t) => t.id !== id))
            }
            onUpdateTerm={(id, field, value) =>
              setTerms((prev) =>
                prev.map((t) =>
                  t.id === id ? { ...t, [field]: value } : t,
                ),
              )
            }
          />
        )}
        {step === 4 && (
          <StepConfirm claims={claims} parties={parties} terms={terms} />
        )}
      </WizardLayout>

      {saveMutation.isSuccess && (
        <div className="mx-auto max-w-3xl rounded-md border border-green-500/30 bg-green-500/10 p-4 text-center text-sm text-green-600">
          Case context saved successfully.
        </div>
      )}
      {saveMutation.isError && (
        <div className="mx-auto max-w-3xl rounded-md border border-destructive/30 bg-destructive/10 p-4 text-center text-sm text-destructive">
          Failed to save: {saveMutation.error.message}
        </div>
      )}
    </div>
  );
}
