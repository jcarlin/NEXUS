import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface VersionMember {
  id: string;
  filename: string;
  version_number: number | null;
  is_final_version: boolean | null;
  created_at: string;
}

interface VersionSelectorProps {
  label: string;
  members: VersionMember[];
  value: string;
  onValueChange: (id: string) => void;
}

export function VersionSelector({
  label,
  members,
  value,
  onValueChange,
}: VersionSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium text-muted-foreground">{label}:</span>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="w-[280px]">
          <SelectValue placeholder="Select a version" />
        </SelectTrigger>
        <SelectContent>
          {members.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.filename}
              {m.version_number != null && ` (v${m.version_number})`}
              {m.is_final_version && " — Final"}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
