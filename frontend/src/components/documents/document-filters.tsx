import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const FILE_EXTENSIONS = [
  "PDF", "DOCX", "DOC", "XLSX", "PPTX", "HTML",
  "EML", "MSG", "TXT", "CSV", "RTF", "PNG", "JPG", "TIFF",
];

interface DocumentFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  fileExtension: string;
  onFileExtensionChange: (value: string) => void;
}

export function DocumentFilters({
  search,
  onSearchChange,
  fileExtension,
  onFileExtensionChange,
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

      <Select value={fileExtension} onValueChange={onFileExtensionChange}>
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Extension" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All types</SelectItem>
          {FILE_EXTENSIONS.map((ext) => (
            <SelectItem key={ext} value={ext.toLowerCase()}>
              {ext}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
