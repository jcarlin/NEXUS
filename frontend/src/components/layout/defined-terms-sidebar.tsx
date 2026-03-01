import { useState } from "react";
import { X, Search, BookOpen } from "lucide-react";
import { useAppStore } from "@/stores/app-store";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface DefinedTerm {
  term: string;
  definition: string;
}

const MOCK_TERMS: DefinedTerm[] = [
  { term: "Affiliate", definition: "Any entity that directly or indirectly controls, is controlled by, or is under common control with the subject entity." },
  { term: "Confidential Information", definition: "Any non-public information disclosed by either party, whether orally or in writing, that is designated as confidential." },
  { term: "Effective Date", definition: "The date on which this Agreement is executed by all parties." },
  { term: "Force Majeure", definition: "Any event beyond the reasonable control of a party, including acts of God, war, terrorism, strikes, or government actions." },
  { term: "Indemnified Party", definition: "The party entitled to indemnification under the terms of this Agreement." },
  { term: "Intellectual Property", definition: "All patents, trademarks, copyrights, trade secrets, and other proprietary rights." },
  { term: "Material Adverse Effect", definition: "Any change, event, or occurrence that has a materially adverse effect on the business, assets, or financial condition of the Company." },
  { term: "Permitted Transferee", definition: "Any affiliate, successor, or assignee approved in writing by the non-transferring party." },
  { term: "Privileged Communication", definition: "Any communication protected by attorney-client privilege, work product doctrine, or other applicable legal privilege." },
  { term: "Responsive Document", definition: "Any document that is relevant to a discovery request and not subject to a valid privilege claim." },
];

export function DefinedTermsSidebar() {
  const open = useAppStore((s) => s.definedTermsOpen);
  const toggleDefinedTerms = useAppStore((s) => s.toggleDefinedTerms);
  const [search, setSearch] = useState("");

  if (!open) return null;

  const filtered = MOCK_TERMS.filter(
    (t) =>
      t.term.toLowerCase().includes(search.toLowerCase()) ||
      t.definition.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="fixed right-0 top-0 z-40 flex h-full w-80 flex-col border-l bg-background shadow-lg">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Defined Terms</h3>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={toggleDefinedTerms}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="border-b px-4 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search terms..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2">
          {filtered.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">
              No matching terms found.
            </p>
          )}
          {filtered.map((item) => (
            <div
              key={item.term}
              className="rounded-md px-3 py-2 hover:bg-muted/50"
            >
              <p className="text-sm font-medium">{item.term}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {item.definition}
              </p>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="border-t px-4 py-2">
        <p className="text-[10px] text-muted-foreground">
          {filtered.length} of {MOCK_TERMS.length} terms
          <span className="float-right">Ctrl+D to toggle</span>
        </p>
      </div>
    </div>
  );
}
