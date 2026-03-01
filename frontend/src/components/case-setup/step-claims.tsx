import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

interface Claim {
  id: string;
  text: string;
}

interface StepClaimsProps {
  claims: Claim[];
  onAdd: () => void;
  onRemove: (id: string) => void;
  onUpdate: (id: string, text: string) => void;
}

export function StepClaims({ claims, onAdd, onRemove, onUpdate }: StepClaimsProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Claims</h2>
        <p className="text-sm text-muted-foreground">
          Define the claims or issues for this case. These help guide retrieval and analysis.
        </p>
      </div>

      <div className="space-y-3">
        {claims.map((claim) => (
          <Card key={claim.id}>
            <CardContent className="flex items-center gap-3 p-4">
              <Input
                value={claim.text}
                onChange={(e) => onUpdate(claim.id, e.target.value)}
                placeholder="Describe the claim or issue..."
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
