import { memo } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { cn } from "@/lib/utils";
import { Database, Key, Link, Box, GitBranch } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Data shapes                                                        */
/* ------------------------------------------------------------------ */

export interface TableNodeData {
  label: string;
  columns: { name: string; type: "pk" | "fk" | "col" | "idx" }[];
  domain?: string;
  rowHint?: string;
  [key: string]: unknown;
}

export interface CollectionNodeData {
  label: string;
  vectors: { name: string; dims: string; distance: string; note?: string }[];
  payload: string[];
  note?: string;
  [key: string]: unknown;
}

export interface GraphLabelNodeData {
  label: string;
  variant: "node" | "relationship";
  properties?: string[];
  [key: string]: unknown;
}

export interface StoreGroupData {
  label: string;
  color: string;
  subtitle?: string;
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/*  Domain color map                                                   */
/* ------------------------------------------------------------------ */

const domainAccent: Record<string, string> = {
  core: "border-l-blue-500",
  auth: "border-l-violet-500",
  audit: "border-l-amber-500",
  ingestion: "border-l-cyan-500",
  query: "border-l-indigo-500",
  entities: "border-l-emerald-500",
  cases: "border-l-rose-500",
  edrm: "border-l-orange-500",
  datasets: "border-l-teal-500",
  production: "border-l-pink-500",
  config: "border-l-slate-400",
  analytics: "border-l-purple-500",
};

/* ------------------------------------------------------------------ */
/*  TableNode — ER-style table card                                    */
/* ------------------------------------------------------------------ */

export type TableNodeType = Node<TableNodeData, "table">;

export const TableNode = memo(function TableNode({
  data,
}: NodeProps<TableNodeType>) {
  const accent = domainAccent[data.domain ?? "core"] ?? "border-l-blue-500";

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card shadow-sm transition-colors",
        "hover:border-primary/40 hover:shadow-md",
        "border-l-[3px] min-w-[150px] max-w-[200px]",
        accent,
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-blue-500 !w-2 !h-2 !border-0"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!bg-blue-500 !w-2 !h-2 !border-0"
      />

      {/* Header */}
      <div className="flex items-center gap-1.5 border-b border-border/50 px-2.5 py-1.5">
        <Database className="h-3 w-3 shrink-0 text-blue-500" />
        <span className="text-[11px] font-bold leading-tight">
          {data.label}
        </span>
        {data.rowHint && (
          <span className="ml-auto text-[9px] text-muted-foreground">
            {data.rowHint}
          </span>
        )}
      </div>

      {/* Columns */}
      <div className="space-y-0 px-2.5 py-1.5">
        {data.columns.map((col) => (
          <div key={col.name} className="flex items-center gap-1.5 py-[1px]">
            {col.type === "pk" && (
              <Key className="h-2.5 w-2.5 shrink-0 text-amber-500" />
            )}
            {col.type === "fk" && (
              <Link className="h-2.5 w-2.5 shrink-0 text-blue-400" />
            )}
            {col.type === "idx" && (
              <GitBranch className="h-2.5 w-2.5 shrink-0 text-emerald-400" />
            )}
            {col.type === "col" && (
              <span className="inline-block h-2.5 w-2.5 shrink-0" />
            )}
            <span
              className={cn(
                "font-mono text-[10px] leading-tight",
                col.type === "pk" && "font-semibold text-foreground",
                col.type === "fk" && "text-blue-600 dark:text-blue-400",
                col.type === "col" && "text-muted-foreground",
                col.type === "idx" && "text-muted-foreground",
              )}
            >
              {col.name}
            </span>
          </div>
        ))}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-blue-500 !w-2 !h-2 !border-0"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!bg-blue-500 !w-2 !h-2 !border-0"
      />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  CollectionNode — Qdrant collection                                 */
/* ------------------------------------------------------------------ */

export type CollectionNodeType = Node<CollectionNodeData, "collection">;

export const CollectionNode = memo(function CollectionNode({
  data,
}: NodeProps<CollectionNodeType>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card shadow-sm transition-colors",
        "hover:border-emerald-500/40 hover:shadow-md",
        "border-l-[3px] border-l-emerald-500 min-w-[180px] max-w-[260px]",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-emerald-500 !w-2 !h-2 !border-0"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!bg-emerald-500 !w-2 !h-2 !border-0"
      />

      {/* Header */}
      <div className="flex items-center gap-1.5 border-b border-border/50 px-2.5 py-1.5">
        <Box className="h-3 w-3 shrink-0 text-emerald-500" />
        <span className="text-[11px] font-bold leading-tight">
          {data.label}
        </span>
      </div>

      {/* Vectors */}
      <div className="space-y-0.5 px-2.5 pt-1.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
          Vectors
        </span>
        {data.vectors.map((v) => (
          <div key={v.name} className="flex items-baseline gap-1">
            <code className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              {v.name}
            </code>
            <span className="text-[9px] text-muted-foreground">
              {v.dims} {v.distance}
            </span>
            {v.note && (
              <span className="text-[8px] italic text-muted-foreground/70">
                {v.note}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Payload */}
      <div className="px-2.5 pb-1.5 pt-1">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
          Payload
        </span>
        <div className="mt-0.5 flex flex-wrap gap-1">
          {data.payload.map((p) => (
            <code
              key={p}
              className="rounded bg-emerald-500/10 px-1 text-[9px] text-emerald-700 dark:text-emerald-300"
            >
              {p}
            </code>
          ))}
        </div>
      </div>

      {data.note && (
        <div className="border-t border-border/30 px-2.5 py-1 text-[9px] italic text-muted-foreground">
          {data.note}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-emerald-500 !w-2 !h-2 !border-0"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!bg-emerald-500 !w-2 !h-2 !border-0"
      />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  GraphLabelNode — Neo4j node / relationship type                    */
/* ------------------------------------------------------------------ */

export type GraphLabelNodeType = Node<GraphLabelNodeData, "graphLabel">;

export const GraphLabelNode = memo(function GraphLabelNode({
  data,
}: NodeProps<GraphLabelNodeType>) {
  const isNode = data.variant === "node";

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card shadow-sm transition-colors",
        "hover:shadow-md min-w-[120px] max-w-[180px]",
        isNode
          ? "border-l-[3px] border-l-purple-500 hover:border-purple-500/40"
          : "border-l-[3px] border-l-rose-400 hover:border-rose-400/40",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className={cn(
          "!w-2 !h-2 !border-0",
          isNode ? "!bg-purple-500" : "!bg-rose-400",
        )}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className={cn(
          "!w-2 !h-2 !border-0",
          isNode ? "!bg-purple-500" : "!bg-rose-400",
        )}
      />

      <div className="px-2.5 py-1.5">
        <div className="flex items-center gap-1.5">
          {isNode ? (
            <span className="text-[9px] font-bold text-purple-500">(:)</span>
          ) : (
            <span className="text-[9px] font-bold text-rose-400">
              -[:]-&gt;
            </span>
          )}
          <span className="text-[11px] font-bold leading-tight">
            {data.label}
          </span>
        </div>
        {data.properties && data.properties.length > 0 && (
          <div className="mt-1 space-y-0">
            {data.properties.map((p) => (
              <div
                key={p}
                className="font-mono text-[9px] text-muted-foreground"
              >
                .{p}
              </div>
            ))}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className={cn(
          "!w-2 !h-2 !border-0",
          isNode ? "!bg-purple-500" : "!bg-rose-400",
        )}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className={cn(
          "!w-2 !h-2 !border-0",
          isNode ? "!bg-purple-500" : "!bg-rose-400",
        )}
      />
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  StoreGroup — swim lane container                                   */
/* ------------------------------------------------------------------ */

export type StoreGroupType = Node<StoreGroupData, "storeGroup">;

const storeColors: Record<string, string> = {
  blue: "border-blue-500/30 bg-blue-500/[0.02]",
  emerald: "border-emerald-500/30 bg-emerald-500/[0.02]",
  purple: "border-purple-500/30 bg-purple-500/[0.02]",
};

const storeLabelBg: Record<string, string> = {
  blue: "bg-blue-950/80",
  emerald: "bg-emerald-950/80",
  purple: "bg-purple-950/80",
};

const storeLabelText: Record<string, string> = {
  blue: "text-blue-600 dark:text-blue-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
  purple: "text-purple-600 dark:text-purple-400",
};

export const StoreGroup = memo(function StoreGroup({
  data,
}: NodeProps<StoreGroupType>) {
  const color = data.color ?? "blue";

  return (
    <div
      className={cn(
        "rounded-xl border-2 border-dashed h-full w-full",
        storeColors[color],
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-baseline gap-2 px-3 pt-2">
        <span
          className={cn(
            "inline-block rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest",
            storeLabelText[color],
            storeLabelBg[color],
          )}
        >
          {data.label}
        </span>
        {data.subtitle && (
          <span className="text-[9px] text-muted-foreground">
            {data.subtitle}
          </span>
        )}
      </div>
    </div>
  );
});
