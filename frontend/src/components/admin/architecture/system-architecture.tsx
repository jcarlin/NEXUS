import { useCallback, useMemo } from "react";
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

import { ArchNode, GroupNode, StorageNode, ExternalNode } from "./arch-nodes";
import { allNodes, allEdges } from "./arch-data";

/* ------------------------------------------------------------------ */
/*  Node type registry                                                 */
/* ------------------------------------------------------------------ */

const nodeTypes: NodeTypes = {
  arch: ArchNode,
  group: GroupNode,
  storage: StorageNode,
  external: ExternalNode,
};

/* ------------------------------------------------------------------ */
/*  MiniMap color resolver                                             */
/* ------------------------------------------------------------------ */

function miniMapColor(node: { type?: string }): string {
  switch (node.type) {
    case "group":
      return "transparent";
    case "storage":
      return "#10b981";
    case "external":
      return "#f59e0b";
    default:
      return "#3b82f6";
  }
}

/* ------------------------------------------------------------------ */
/*  Legend                                                              */
/* ------------------------------------------------------------------ */

const LEGEND = [
  { color: "bg-blue-500", label: "Request flow" },
  { color: "bg-emerald-500", label: "Data writes" },
  { color: "bg-amber-500", label: "AI / ML calls" },
  { color: "bg-gray-500", label: "Async dispatch" },
  { color: "bg-purple-500", label: "Observability" },
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
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

interface SystemArchitectureProps {
  flagMap: Map<string, boolean>;
}

export function SystemArchitecture({ flagMap: _flagMap }: SystemArchitectureProps) {
  // Set z-index: group nodes at 0 (behind edges), child nodes at 10 (above edges)
  const nodes = useMemo(
    () =>
      allNodes.map((n) => ({
        ...n,
        zIndex: n.type === "group" ? 0 : 10,
      })),
    [],
  );
  const edges = useMemo(() => allEdges, []);

  // Detect dark mode from document class list
  const colorMode: ColorMode = useMemo(() => {
    if (typeof document !== "undefined" && document.documentElement.classList.contains("dark")) {
      return "dark";
    }
    return "light";
  }, []);

  // Prevent node dragging (static architecture diagram)
  const onNodeDragStart = useCallback(
    (_: React.MouseEvent, __: unknown) => undefined,
    [],
  );

  return (
    <div className="arch-diagram relative h-[calc(100vh-220px)] min-h-[600px] rounded-xl border border-border bg-background">
      {/* Force nodes layer above edges layer via CSS */}
      <style>{`
        .arch-diagram .react-flow__edges { z-index: 1 !important; }
        .arch-diagram .react-flow__edgelabel-renderer { z-index: 2 !important; }
        .arch-diagram .react-flow__nodes { z-index: 3 !important; }
      `}</style>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.15}
        maxZoom={2.5}
        colorMode={colorMode}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        onNodeDragStart={onNodeDragStart}
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
    </div>
  );
}
