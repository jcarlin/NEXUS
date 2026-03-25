import { memo } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { cn } from "@/lib/utils";
import {
  Database,
  Cloud,
  Server,
  Cpu,
  Eye,
  Shield,
  Box,
  Workflow,
  HardDrive,
  Brain,
  Bot,
  Globe,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Data shapes                                                        */
/* ------------------------------------------------------------------ */

export interface ArchNodeData {
  label: string;
  description?: string;
  tech?: string;
  variant?: "default" | "primary" | "core" | "intelligence" | "workflow" | "management" | "agent";
  icon?: string;
  items?: string[];
  disabled?: boolean;
  [key: string]: unknown;
}

export interface GroupNodeData {
  label: string;
  color?: string;
  [key: string]: unknown;
}

export interface StorageNodeData {
  label: string;
  description?: string;
  tech?: string;
  icon?: string;
  [key: string]: unknown;
}

export interface ExternalNodeData {
  label: string;
  description?: string;
  providers?: string[];
  icon?: string;
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/*  Icon resolver                                                      */
/* ------------------------------------------------------------------ */

const ICON_MAP: Record<string, typeof Server> = {
  server: Server,
  database: Database,
  cloud: Cloud,
  cpu: Cpu,
  eye: Eye,
  shield: Shield,
  box: Box,
  workflow: Workflow,
  drive: HardDrive,
  brain: Brain,
  bot: Bot,
  globe: Globe,
};

function NodeIcon({ name, className }: { name?: string; className?: string }) {
  if (!name) return null;
  const Icon = ICON_MAP[name];
  if (!Icon) return null;
  return <Icon className={cn("h-3.5 w-3.5 shrink-0", className)} />;
}

/* ------------------------------------------------------------------ */
/*  Variant styles                                                     */
/* ------------------------------------------------------------------ */

const variantBorder: Record<string, string> = {
  default: "border-l-blue-500/60",
  primary: "border-l-blue-500 border-l-[3px]",
  core: "border-l-blue-500 border-l-[3px]",
  intelligence: "border-l-violet-500 border-l-[3px]",
  workflow: "border-l-cyan-500 border-l-[3px]",
  management: "border-l-slate-400 border-l-[3px]",
  agent: "border-l-amber-500 border-l-[3px]",
};

/* ------------------------------------------------------------------ */
/*  ArchNode — standard service / module node                          */
/* ------------------------------------------------------------------ */

export type ArchNodeType = Node<ArchNodeData, "arch">;

export const ArchNode = memo(function ArchNode({ data }: NodeProps<ArchNodeType>) {
  const variant = data.variant ?? "default";

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card px-3 py-2 shadow-sm transition-colors",
        "hover:border-primary/40 hover:shadow-md",
        "min-w-[140px] max-w-[220px]",
        variantBorder[variant],
        data.disabled && "border-dashed opacity-45",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-2 !h-2 !border-0" />

      <div className="flex items-center gap-1.5">
        <NodeIcon name={data.icon} className="text-muted-foreground" />
        <span className="text-xs font-semibold leading-tight">{data.label}</span>
      </div>

      {data.description && (
        <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{data.description}</p>
      )}

      {data.tech && (
        <p className="mt-0.5 text-[10px] font-mono text-blue-600/70 dark:text-blue-400/70">{data.tech}</p>
      )}

      {data.items && data.items.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {data.items.map((item) => (
            <span
              key={item}
              className="rounded bg-muted/60 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground"
            >
              {item}
            </span>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Right} id="right" className="!bg-blue-500 !w-2 !h-2 !border-0" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-blue-500 !w-2 !h-2 !border-0" />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  GroupNode — section container                                      */
/* ------------------------------------------------------------------ */

export type GroupNodeType = Node<GroupNodeData, "group">;

const groupColors: Record<string, string> = {
  blue: "border-blue-500/30 bg-blue-500/[0.03]",
  emerald: "border-emerald-500/30 bg-emerald-500/[0.03]",
  amber: "border-amber-500/30 bg-amber-500/[0.03]",
  violet: "border-violet-500/30 bg-violet-500/[0.03]",
  cyan: "border-cyan-500/30 bg-cyan-500/[0.03]",
  slate: "border-slate-400/30 bg-slate-400/[0.03]",
  purple: "border-purple-500/30 bg-purple-500/[0.03]",
  rose: "border-rose-500/30 bg-rose-500/[0.03]",
};

const groupLabelBg: Record<string, string> = {
  blue: "bg-blue-950/80",
  emerald: "bg-emerald-950/80",
  amber: "bg-amber-950/80",
  violet: "bg-violet-950/80",
  cyan: "bg-cyan-950/80",
  slate: "bg-slate-900/80",
  purple: "bg-purple-950/80",
  rose: "bg-rose-950/80",
};

const groupLabelColors: Record<string, string> = {
  blue: "text-blue-600 dark:text-blue-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
  amber: "text-amber-600 dark:text-amber-400",
  violet: "text-violet-600 dark:text-violet-400",
  cyan: "text-cyan-600 dark:text-cyan-400",
  slate: "text-slate-500 dark:text-slate-400",
  purple: "text-purple-600 dark:text-purple-400",
  rose: "text-rose-600 dark:text-rose-400",
};

export const GroupNode = memo(function GroupNode({ data }: NodeProps<GroupNodeType>) {
  const color = data.color ?? "blue";

  return (
    <div
      className={cn(
        "rounded-xl border-2 border-dashed",
        "h-full w-full",
        groupColors[color],
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 px-3 pt-2">
        <span
          className={cn(
            "inline-block rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest",
            groupLabelColors[color],
            groupLabelBg[color],
          )}
        >
          {data.label}
        </span>
      </div>
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  StorageNode — data store node                                      */
/* ------------------------------------------------------------------ */

export type StorageNodeType = Node<StorageNodeData, "storage">;

export const StorageNode = memo(function StorageNode({ data }: NodeProps<StorageNodeType>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card px-3 py-2 shadow-sm transition-colors",
        "hover:border-emerald-500/40 hover:shadow-md",
        "border-l-[3px] border-l-emerald-500",
        "min-w-[140px] max-w-[200px]",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-2 !h-2 !border-0" />

      <div className="flex items-center gap-1.5">
        <NodeIcon name={data.icon ?? "database"} className="text-emerald-500" />
        <span className="text-xs font-semibold leading-tight">{data.label}</span>
      </div>

      {data.tech && (
        <p className="mt-0.5 text-[10px] font-mono text-emerald-600 dark:text-emerald-400">{data.tech}</p>
      )}

      {data.description && (
        <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{data.description}</p>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500 !w-2 !h-2 !border-0" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-emerald-500 !w-2 !h-2 !border-0" />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  ExternalNode — external service (LLM providers, LangSmith, etc.)   */
/* ------------------------------------------------------------------ */

export type ExternalNodeType = Node<ExternalNodeData, "external">;

export const ExternalNode = memo(function ExternalNode({ data }: NodeProps<ExternalNodeType>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card px-3 py-2 shadow-sm transition-colors",
        "hover:border-amber-500/40 hover:shadow-md",
        "border-l-[3px] border-l-amber-500",
        "min-w-[140px] max-w-[220px]",
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-amber-500 !w-2 !h-2 !border-0" />

      <div className="flex items-center gap-1.5">
        <NodeIcon name={data.icon ?? "cloud"} className="text-amber-500" />
        <span className="text-xs font-semibold leading-tight">{data.label}</span>
      </div>

      {data.description && (
        <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{data.description}</p>
      )}

      {data.providers && data.providers.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {data.providers.map((p) => (
            <span
              key={p}
              className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 dark:text-amber-300"
            >
              {p}
            </span>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-amber-500 !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Bottom} id="bottom" className="!bg-amber-500 !w-2 !h-2 !border-0" />
    </div>
  );
});
