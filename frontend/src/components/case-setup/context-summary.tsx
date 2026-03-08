import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ContextSummaryProps {
  context: {
    status: string;
    claims?: Array<{ claim_number: number; claim_label: string; claim_text: string }>;
    parties?: Array<{ name: string; role: string }>;
    defined_terms?: Array<{ term: string; definition: string }>;
    key_dates?: Array<{ date: string; description: string }>;
  };
  onRerun: () => void;
}

export function ContextSummary({ context, onRerun }: ContextSummaryProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Case Context</h2>
          <p className="text-sm text-muted-foreground">
            Context has been configured for this matter.
          </p>
        </div>
        <Button variant="outline" onClick={onRerun}>
          Re-run Setup
        </Button>
      </div>

      {context.claims && context.claims.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Claims ({context.claims.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {context.claims.map((claim) => (
              <div key={claim.claim_number} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">#{claim.claim_number}</Badge>
                  {claim.claim_label && (
                    <span className="text-sm font-medium">{claim.claim_label}</span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">{claim.claim_text}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {context.parties && context.parties.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Parties ({context.parties.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {context.parties.map((party) => (
                <Badge key={party.name} variant="outline">
                  {party.name} ({party.role})
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {context.defined_terms && context.defined_terms.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Defined Terms ({context.defined_terms.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {context.defined_terms.map((dt) => (
              <div key={dt.term}>
                <span className="font-medium text-sm">{dt.term}:</span>{" "}
                <span className="text-sm text-muted-foreground">{dt.definition}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {context.key_dates && context.key_dates.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Key Dates ({context.key_dates.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {context.key_dates.map((kd, i) => (
              <div key={i} className="flex gap-2 text-sm">
                <span className="font-mono text-muted-foreground whitespace-nowrap">{kd.date}</span>
                <span>{kd.description}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
