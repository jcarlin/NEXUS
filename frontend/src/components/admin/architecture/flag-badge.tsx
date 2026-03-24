import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface FlagBadgeProps {
  name: string;
  enabled: boolean;
  label?: string;
  description?: string;
  onToggle?: (flagName: string, newValue: boolean) => void;
}

export function FlagBadge({ name, enabled, label, description, onToggle }: FlagBadgeProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help items-center gap-1.5">
          <Badge
            variant="outline"
            className={
              enabled
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 text-[10px] dark:text-emerald-400"
                : "border-muted-foreground/20 bg-muted/50 text-muted-foreground text-[10px]"
            }
          >
            {label ?? (enabled ? "ON" : "OFF")}
          </Badge>
          {onToggle && (
            <Switch
              checked={enabled}
              onCheckedChange={(checked) => onToggle(name, checked)}
              className="h-3.5 w-7 data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-muted-foreground/30"
              aria-label={`Toggle ${name}`}
            />
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <p className="font-mono text-xs">{name}</p>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </TooltipContent>
    </Tooltip>
  );
}
