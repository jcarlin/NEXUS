import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

interface Claim {
  id: string;
  claim_number: number;
  claim_label: string;
  claim_text: string;
}

interface StepClaimsProps {
  claims: Claim[];
  onAdd: () => void;
  onRemove: (id: string) => void;
  onUpdate: (id: string, field: "claim_label" | "claim_text", value: string) => void;
}

export function StepClaims({ claims, onAdd, onRemove, onUpdate }: StepClaimsProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Claims</h2>
        <p className="text-sm text-muted-foreground">
          Define the claims or causes of action for this case. These help guide retrieval and analysis.
        </p>
      </div>

      <div className="space-y-3">
        {claims.map((claim) => (
          <Card key={claim.id}>
            <CardContent className="space-y-3 p-4">
              <div className="flex items-center gap-3">
                <span className="shrink-0 text-xs font-mono text-muted-foreground w-6">
                  #{claim.claim_number}
                </span>
                <Input
                  value={claim.claim_label}
                  onChange={(e) => onUpdate(claim.id, "claim_label", e.target.value)}
                  placeholder="Claim label (e.g., Fraud, Breach of Contract)"
                  className="flex-1"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => onRemove(claim.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <Input
                value={claim.claim_text}
                onChange={(e) => onUpdate(claim.id, "claim_text", e.target.value)}
                placeholder="Full text of the claim or cause of action..."
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="outline" onClick={onAdd} className="w-full">
        <Plus className="mr-2 h-4 w-4" />
        Add Claim
      </Button>
    </div>
  );
}
