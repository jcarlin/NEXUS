import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface FlagBadgeProps {
  name: string;
  enabled: boolean;
  label?: string;
}

export function FlagBadge({ name, enabled, label }: FlagBadgeProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
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
      </TooltipTrigger>
      <TooltipContent side="top">
        <p className="text-xs font-mono">{name}</p>
      </TooltipContent>
    </Tooltip>
  );
}
