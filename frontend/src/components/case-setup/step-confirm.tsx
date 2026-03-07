import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Claim {
  id: string;
  claim_number: number;
  claim_label: string;
  claim_text: string;
}

interface Party {
  id: string;
  name: string;
  role: string;
}

interface DefinedTerm {
  id: string;
  term: string;
  definition: string;
}

interface StepConfirmProps {
  claims: Claim[];
  parties: Party[];
  terms: DefinedTerm[];
}

export function StepConfirm({ claims, parties, terms }: StepConfirmProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Review & Confirm</h2>
        <p className="text-sm text-muted-foreground">
          Review the case configuration before saving.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">
            Claims
            <Badge variant="secondary" className="ml-2">
              {claims.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {claims.length === 0 ? (
            <p className="text-sm text-muted-foreground">No claims defined.</p>
          ) : (
            <ul className="space-y-2">
              {claims.map((claim) => (
                <li key={claim.id} className="text-sm">
                  <span className="mr-2 font-mono text-xs text-muted-foreground">
                    {claim.claim_number}.
                  </span>
                  {claim.claim_label && (
                    <span className="mr-1 font-medium">{claim.claim_label}:</span>
                  )}
                  {claim.claim_text || <span className="italic text-muted-foreground">Empty claim</span>}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">
              Parties
              <Badge variant="secondary" className="ml-2">
                {parties.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {parties.length === 0 ? (
              <p className="text-sm text-muted-foreground">No parties defined.</p>
            ) : (
              <ul className="space-y-1.5">
                {parties.map((party) => (
                  <li key={party.id} className="flex items-center gap-2 text-sm">
                    <span className="font-medium">{party.name || "Unnamed"}</span>
                    {party.role && (
                      <Badge variant="outline" className="text-[10px]">
                        {party.role}
                      </Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">
              Defined Terms
              <Badge variant="secondary" className="ml-2">
                {terms.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {terms.length === 0 ? (
              <p className="text-sm text-muted-foreground">No terms defined.</p>
            ) : (
              <dl className="space-y-2">
                {terms.map((item) => (
                  <div key={item.id}>
                    <dt className="text-sm font-medium">{item.term || "Unnamed"}</dt>
                    <dd className="text-xs text-muted-foreground">
                      {item.definition || "No definition"}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
