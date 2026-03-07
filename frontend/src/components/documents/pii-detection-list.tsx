import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";

interface PIIDetection {
  category: string;
  text: string;
  start: number;
  end: number;
  page_number: number;
  confidence: number;
}

interface Props {
  detections: PIIDetection[];
  selected: Set<number>;
  onToggle: (index: number) => void;
}

const categoryColors: Record<string, string> = {
  ssn: "bg-red-500/15 text-red-700",
  phone: "bg-blue-500/15 text-blue-700",
  email: "bg-purple-500/15 text-purple-700",
  dob: "bg-orange-500/15 text-orange-700",
  medical: "bg-pink-500/15 text-pink-700",
  financial: "bg-green-500/15 text-green-700",
};

function maskText(text: string): string {
  if (text.length <= 4) return "****";
  return text.slice(0, 2) + "*".repeat(text.length - 4) + text.slice(-2);
}

export function PiiDetectionList({ detections, selected, onToggle }: Props) {
  return (
    <div className="space-y-1 max-h-[300px] overflow-y-auto">
      {detections.map((d, i) => (
        <label
          key={i}
          className="flex items-center gap-3 rounded-md border px-3 py-2 cursor-pointer hover:bg-muted/50"
        >
          <Checkbox
            checked={selected.has(i)}
            onCheckedChange={() => onToggle(i)}
          />
          <Badge
            variant="secondary"
            className={categoryColors[d.category] ?? ""}
          >
            {d.category.toUpperCase()}
          </Badge>
          <span className="flex-1 font-mono text-xs truncate">
            {maskText(d.text)}
          </span>
          <span className="text-xs text-muted-foreground">
            p.{d.page_number}
          </span>
          <span className="text-xs text-muted-foreground">
            {Math.round(d.confidence * 100)}%
          </span>
        </label>
      ))}
    </div>
  );
}
