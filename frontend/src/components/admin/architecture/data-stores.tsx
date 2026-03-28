import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  type ColorMode,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  TableNode,
  CollectionNode,
  GraphLabelNode,
  StoreGroup,
} from "./schema-nodes";
import { allSchemaNodes, allSchemaEdges } from "./schema-data";

/* ------------------------------------------------------------------ */
/*  Node type registry                                                 */
/* ------------------------------------------------------------------ */

const nodeTypes: NodeTypes = {
  table: TableNode,
  collection: CollectionNode,
  graphLabel: GraphLabelNode,
  storeGroup: StoreGroup,
};

/* ------------------------------------------------------------------ */
/*  MiniMap color resolver                                             */
/* ------------------------------------------------------------------ */

function miniMapColor(node: { type?: string }): string {
  switch (node.type) {
    case "storeGroup":
      return "transparent";
    case "collection":
      return "#10b981";
    case "graphLabel":
      return "#a855f7";
    default:
      return "#3b82f6";
  }
}

/* ------------------------------------------------------------------ */
/*  Legend                                                              */
/* ------------------------------------------------------------------ */

const LEGEND = [
  { color: "bg-blue-400", label: "Foreign key" },
  { color: "bg-amber-500", label: "Cross-store link" },
  { color: "bg-purple-400", label: "Graph relationship" },
] as const;

function Legend() {
  return (
    <div className="absolute bottom-3 left-3 z-10 flex items-center gap-3 rounded-lg border border-border bg-card/90 px-3 py-2 text-[10px] backdrop-blur-sm">
      <span className="font-semibold text-muted-foreground">Edges:</span>
      {LEGEND.map(({ color, label }) => (
        <span key={label} className="flex items-center gap-1">
          <span className={`inline-block h-2 w-4 rounded-sm ${color}`} />
          {label}
        </span>
      ))}
      <span className="ml-2 flex items-center gap-1 border-l border-border pl-2">
        <span className="inline-block h-2 w-4 rounded-sm bg-amber-500" style={{ backgroundImage: "repeating-linear-gradient(90deg, transparent, transparent 3px, var(--color-card) 3px, var(--color-card) 5px)" }} />
        animated = cross-store
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Column legend                                                      */
/* ------------------------------------------------------------------ */

function ColumnLegend() {
  return (
    <div className="absolute top-3 right-3 z-10 flex items-center gap-3 rounded-lg border border-border bg-card/90 px-3 py-2 text-[10px] backdrop-blur-sm">
      <span className="font-semibold text-muted-foreground">Columns:</span>
      <span className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
        PK
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full bg-blue-400" />
        FK
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
        Indexed
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DataStores() {
  const nodes = useMemo(
    () =>
      allSchemaNodes.map((n) => ({
        ...n,
        zIndex: n.type === "storeGroup" ? 0 : 10,
      })),
    [],
  );
  const edges = useMemo(() => allSchemaEdges, []);

  const colorMode: ColorMode = useMemo(() => {
    if (
      typeof document !== "undefined" &&
      document.documentElement.classList.contains("dark")
    ) {
      return "dark";
    }
    return "light";
  }, []);

  return (
    <div className="schema-diagram relative h-[calc(100vh-220px)] min-h-[600px] rounded-xl border border-border bg-background">
      <style>{`
        .schema-diagram .react-flow__edges { z-index: 1 !important; }
        .schema-diagram .react-flow__edgelabel-renderer { z-index: 2 !important; }
        .schema-diagram .react-flow__nodes { z-index: 3 !important; }
      `}</style>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.1}
        maxZoom={2.5}
        colorMode={colorMode}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls
          showInteractive={false}
          className="!border-border !bg-card !shadow-md [&>button]:!border-border [&>button]:!bg-card [&>button]:!fill-foreground hover:[&>button]:!bg-muted"
        />
        <MiniMap
          nodeColor={miniMapColor}
          maskColor="rgba(0,0,0,0.08)"
          className="!border-border !bg-card !shadow-md"
          pannable
          zoomable
        />
      </ReactFlow>
      <Legend />
      <ColumnLegend />
    </div>
  );
}
