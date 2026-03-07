import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PartyRole } from "@/api/generated/schemas";

const PARTY_ROLES: { value: PartyRole; label: string }[] = [
  { value: "plaintiff", label: "Plaintiff" },
  { value: "defendant", label: "Defendant" },
  { value: "third_party", label: "Third Party" },
  { value: "witness", label: "Witness" },
  { value: "counsel", label: "Counsel" },
];

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

interface StepPartiesTermsProps {
  parties: Party[];
  onAddParty: () => void;
  onRemoveParty: (id: string) => void;
  onUpdateParty: (id: string, field: "name" | "role", value: string) => void;
  terms: DefinedTerm[];
  onAddTerm: () => void;
  onRemoveTerm: (id: string) => void;
  onUpdateTerm: (id: string, field: "term" | "definition", value: string) => void;
}

export function StepPartiesTerms({
  parties,
  onAddParty,
  onRemoveParty,
  onUpdateParty,
  terms,
  onAddTerm,
  onRemoveTerm,
  onUpdateTerm,
}: StepPartiesTermsProps) {
  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
      {/* Parties */}
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">Parties</h2>
          <p className="text-sm text-muted-foreground">
            Key parties involved in the case.
          </p>
        </div>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {parties.map((party) => (
                <TableRow key={party.id}>
                  <TableCell className="p-2">
                    <Input
                      value={party.name}
                      onChange={(e) =>
                        onUpdateParty(party.id, "name", e.target.value)
                      }
                      placeholder="Party name"
                      className="h-8 text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-2">
                    <Select
                      value={party.role}
                      onValueChange={(val) =>
                        onUpdateParty(party.id, "role", val)
                      }
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue placeholder="Select role" />
                      </SelectTrigger>
                      <SelectContent>
                        {PARTY_ROLES.map((r) => (
                          <SelectItem key={r.value} value={r.value}>
                            {r.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="p-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => onRemoveParty(party.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {parties.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-sm text-muted-foreground">
                    No parties added yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <Button variant="outline" size="sm" onClick={onAddParty}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add Party
        </Button>
      </div>

      {/* Defined Terms */}
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">Defined Terms</h2>
          <p className="text-sm text-muted-foreground">
            Key terms and their definitions for the case.
          </p>
        </div>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Term</TableHead>
                <TableHead>Definition</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {terms.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="p-2">
                    <Input
                      value={item.term}
                      onChange={(e) =>
                        onUpdateTerm(item.id, "term", e.target.value)
                      }
                      placeholder="Term"
                      className="h-8 text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-2">
                    <Input
                      value={item.definition}
                      onChange={(e) =>
                        onUpdateTerm(item.id, "definition", e.target.value)
                      }
                      placeholder="Definition"
                      className="h-8 text-sm"
                    />
                  </TableCell>
                  <TableCell className="p-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => onRemoveTerm(item.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {terms.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-sm text-muted-foreground">
                    No defined terms added yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <Button variant="outline" size="sm" onClick={onAddTerm}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add Term
        </Button>
      </div>
    </div>
  );
}
