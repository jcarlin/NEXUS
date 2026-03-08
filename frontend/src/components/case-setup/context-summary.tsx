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
    timeline?: Array<{ date: string; event_text: string; source_page?: number }>;
  };
  onRerun: () => void;
}

export function ContextSummary({ context, onRerun }: ContextSummaryProps) {
  // Deduplicate parties by name+role and terms by term
  const uniqueParties = context.parties
    ? [...new Map(context.parties.map((p) => [`${p.name}|${p.role}`, p])).values()]
    : [];
  const uniqueTerms = context.defined_terms
    ? [...new Map(context.defined_terms.map((t) => [t.term, t])).values()]
    : [];

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
            {context.claims.map((claim, i) => (
              <div key={i} className="space-y-1">
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

      {uniqueParties.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Parties ({uniqueParties.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {uniqueParties.map((party, i) => (
                <Badge key={i} variant="outline">
                  {party.name} ({party.role})
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {uniqueTerms.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Defined Terms ({uniqueTerms.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {uniqueTerms.map((dt, i) => (
              <div key={i}>
                <span className="font-medium text-sm">{dt.term}:</span>{" "}
                <span className="text-sm text-muted-foreground">{dt.definition}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {(() => {
        const dates = context.key_dates ?? context.timeline?.map((t) => ({ date: t.date, description: t.event_text }));
        if (!dates || dates.length === 0) return null;
        return (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline ({dates.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {dates.map((kd, i) => (
                <div key={i} className="flex gap-2 text-sm">
                  <span className="font-mono text-muted-foreground whitespace-nowrap">{kd.date}</span>
                  <span>{kd.description}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        );
      })()}
    </div>
  );
}
