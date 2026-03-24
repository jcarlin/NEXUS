import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { FlagBadge } from "./flag-badge";

interface NodeFlag {
  name: string;
  enabled: boolean;
  label?: string;
  onToggle?: (flagName: string, newValue: boolean) => void;
}

interface PipelineNodeProps {
  title: string;
  children: ReactNode;
  flags?: NodeFlag[];
  disabled?: boolean;
  variant?: "default" | "primary" | "store";
  className?: string;
}

const variantStyles = {
  default: "border-l-blue-500/60",
  primary: "border-l-blue-500 border-l-[3px]",
  store: "border-l-emerald-500/60",
};

export function PipelineNode({
  title,
  children,
  flags,
  disabled,
  variant = "default",
  className,
}: PipelineNodeProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-4 transition-all duration-150",
        "hover:border-primary/40 hover:shadow-sm",
        variantStyles[variant],
        disabled && "border-dashed opacity-45 cursor-not-allowed hover:shadow-none hover:border-border",
        className,
      )}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {disabled && (
          <span className="text-[10px] font-medium text-muted-foreground">(off)</span>
        )}
        {flags?.map((f) => <FlagBadge key={f.name} {...f} />)}
      </div>
      <div className="text-xs leading-relaxed text-muted-foreground">{children}</div>
    </div>
  );
}

export function Arrow({ dim }: { dim?: boolean }) {
  return (
    <div className="flex justify-center py-1">
      <div
        className={cn(
          "h-5 w-0.5",
          dim ? "bg-muted-foreground/30" : "bg-blue-500/60",
        )}
      />
    </div>
  );
}
