import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Maximize2, ZoomIn, ZoomOut, Lock, Unlock } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";

const ENTITY_TYPES = [
  { value: "person", label: "Person", color: "#60a5fa" },
  { value: "organization", label: "Organization", color: "#34d399" },
  { value: "location", label: "Location", color: "#fb923c" },
  { value: "date", label: "Date", color: "#a78bfa" },
  { value: "monetary_amount", label: "Money", color: "#f472b6" },
] as const;

interface GraphControlsProps {
  activeTypes: Set<string>;
  onToggleType: (type: string) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  editMode?: boolean;
  onToggleEditMode?: () => void;
}

export function GraphControls({
  activeTypes,
  onToggleType,
  onZoomIn,
  onZoomOut,
  onFitView,
  editMode,
  onToggleEditMode,
}: GraphControlsProps) {
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role === "admin" || user?.role === "attorney";
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border p-3">
      <div className="flex items-center gap-4 flex-wrap">
        {ENTITY_TYPES.map((t) => (
          <div key={t.value} className="flex items-center gap-1.5">
            <Checkbox
              id={`type-${t.value}`}
              checked={activeTypes.has(t.value)}
              onCheckedChange={() => onToggleType(t.value)}
            />
            <Label
              htmlFor={`type-${t.value}`}
              className="text-xs cursor-pointer flex items-center gap-1"
            >
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: t.color }}
              />
              {t.label}
            </Label>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1">
        {canEdit && onToggleEditMode && (
          <Button
            variant={editMode ? "default" : "outline"}
            size="icon"
            className="h-7 w-7"
            onClick={onToggleEditMode}
            title={editMode ? "Exit edit mode" : "Enter edit mode"}
          >
            {editMode ? <Unlock className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
          </Button>
        )}
        <Button variant="outline" size="icon" className="h-7 w-7" onClick={onZoomIn}>
          <ZoomIn className="h-3.5 w-3.5" />
        </Button>
        <Button variant="outline" size="icon" className="h-7 w-7" onClick={onZoomOut}>
          <ZoomOut className="h-3.5 w-3.5" />
        </Button>
        <Button variant="outline" size="icon" className="h-7 w-7" onClick={onFitView}>
          <Maximize2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
