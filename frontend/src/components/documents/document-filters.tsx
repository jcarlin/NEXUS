import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const DOC_TYPES = ["pdf", "docx", "xlsx", "pptx", "html", "eml", "msg", "rtf", "csv", "txt"];
const PRIVILEGE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "privileged", label: "Privileged" },
  { value: "work_product", label: "Work Product" },
  { value: "none", label: "Not Privileged" },
];

interface DocumentFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  docType: string;
  onDocTypeChange: (value: string) => void;
  privilege: string;
  onPrivilegeChange: (value: string) => void;
}

export function DocumentFilters({
  search,
  onSearchChange,
  docType,
  onDocTypeChange,
  privilege,
  onPrivilegeChange,
}: DocumentFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search documents..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9"
        />
      </div>

      <Select value={docType} onValueChange={onDocTypeChange}>
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Type" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All types</SelectItem>
          {DOC_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {t.toUpperCase()}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={privilege} onValueChange={onPrivilegeChange}>
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Privilege" />
        </SelectTrigger>
        <SelectContent>
          {PRIVILEGE_OPTIONS.map((p) => (
            <SelectItem key={p.value} value={p.value}>
              {p.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
