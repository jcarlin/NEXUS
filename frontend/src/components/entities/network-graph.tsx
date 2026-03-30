import { useEffect, useRef, useCallback, useImperativeHandle, forwardRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { select, type Selection } from "d3-selection";
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide, type SimulationNodeDatum, type SimulationLinkDatum, type Simulation } from "d3-force";
import { scaleSqrt } from "d3-scale";
import { zoom, zoomIdentity, type D3ZoomEvent, type ZoomBehavior } from "d3-zoom";
import { drag } from "d3-drag";
import "d3-transition";
import { ENTITY_COLORS, entityColor } from "@/lib/colors";
import { useContainerSize } from "@/hooks/use-container-size";
import type { EntityResponse, EntityConnection } from "@/types";

interface GraphNode extends SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  mention_count: number;
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  relationship_type: string;
  weight: number;
}

export interface NetworkGraphHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

interface NetworkGraphProps {
  entities: EntityResponse[];
  connections: EntityConnection[];
  activeTypes: Set<string>;
  onNodeContextMenu?: (event: MouseEvent, node: { name: string; type: string }) => void;
}

export const NetworkGraph = forwardRef<NetworkGraphHandle, NetworkGraphProps>(
  function NetworkGraph({ entities, connections, activeTypes, onNodeContextMenu }, ref) {
    const svgRef = useRef<SVGSVGElement>(null);
    const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
    const simulationRef = useRef<Simulation<GraphNode, GraphLink> | null>(null);
    const nodeSelRef = useRef<Selection<SVGGElement, GraphNode, SVGGElement, unknown> | null>(null);
    const linkSelRef = useRef<Selection<SVGLineElement, GraphLink, SVGGElement, unknown> | null>(null);
    const navigate = useNavigate({});
    const { ref: containerRef, width: containerWidth, height: containerHeight } = useContainerSize();
    const activeTypesRef = useRef(activeTypes);
    activeTypesRef.current = activeTypes;

    const zoomIn = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      select(svg)
        .transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 1.4);
    }, []);

    const zoomOut = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      select(svg)
        .transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 0.7);
    }, []);

    const fitView = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      select(svg)
        .transition()
        .duration(500)
        .call(zoomRef.current.transform, zoomIdentity);
    }, []);

    useImperativeHandle(ref, () => ({ zoomIn, zoomOut, fitView }), [
      zoomIn,
      zoomOut,
      fitView,
    ]);

    // Data effect: rebuild simulation when entities/connections/dimensions change
    useEffect(() => {
      const svg = svgRef.current;
      if (!svg || containerWidth === 0 || containerHeight === 0) return;

      const width = containerWidth;
      const height = containerHeight;

      // Build ALL nodes (no activeTypes filtering — that's handled by the filter effect)
      const nodeMap = new Map<string, GraphNode>();
      for (const e of entities) {
        nodeMap.set(e.name, {
          id: e.id,
          name: e.name,
          type: e.type,
          mention_count: e.mention_count,
        });
      }

      const entityNames = new Set(entities.map((e) => e.name));
      const filteredConnections = connections.filter(
        (c) => entityNames.has(c.source) && entityNames.has(c.target),
      );

      const nodes = Array.from(nodeMap.values());
      const links: GraphLink[] = filteredConnections.map((c) => ({
        source: c.source,
        target: c.target,
        relationship_type: c.relationship_type,
        weight: c.weight,
      }));

      // Clear previous render
      const sel = select(svg);
      sel.selectAll("*").remove();

      // Size scale for nodes
      const maxMentions = Math.max(...nodes.map((n) => n.mention_count), 1);
      const radiusScale = scaleSqrt()
        .domain([0, maxMentions])
        .range([5, 24]);

      // Zoom behavior
      const zoomBehavior = zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 8])
        .on("zoom", (event: D3ZoomEvent<SVGSVGElement, unknown>) => {
          g.attr("transform", event.transform.toString());
        });
      zoomRef.current = zoomBehavior;
      sel.attr("width", width).attr("height", height).call(zoomBehavior);

      const g = sel.append("g");

      // Simulation
      const simulation = forceSimulation<GraphNode>(nodes)
        .force(
          "link",
          forceLink<GraphNode, GraphLink>(links)
            .id((d) => d.name)
            .distance(120),
        )
        .force("charge", forceManyBody().strength(-300))
        .force("center", forceCenter(width / 2, height / 2))
        .force(
          "collide",
          forceCollide<GraphNode>((d) => radiusScale(d.mention_count) + 4),
        );

      // Links
      const link = g
        .selectAll<SVGLineElement, GraphLink>("line")
        .data(links)
        .join("line")
        .attr("stroke", "var(--color-border)")
        .attr("stroke-opacity", 0.5)
        .attr("stroke-width", (d) =>
          Math.max(0.5, Math.min(d.weight * 1.5, 5)),
        );

      // Node groups
      const node = g
        .selectAll<SVGGElement, GraphNode>("g.node")
        .data(nodes)
        .join("g")
        .attr("class", "node")
        .style("cursor", "pointer")
        .call(
          drag<SVGGElement, GraphNode>()
            .on("start", (event, d) => {
              if (!event.active) simulation.alphaTarget(0.3).restart();
              d.fx = d.x;
              d.fy = d.y;
            })
            .on("drag", (event, d) => {
              d.fx = event.x;
              d.fy = event.y;
            })
            .on("end", (event, d) => {
              if (!event.active) simulation.alphaTarget(0);
              d.fx = null;
              d.fy = null;
            }),
        );

      // Circles
      node
        .append("circle")
        .attr("r", (d) => radiusScale(d.mention_count))
        .attr("fill", (d) => entityColor(d.type))
        .attr("fill-opacity", 0.85)
        .attr("stroke", (d) => entityColor(d.type))
        .attr("stroke-opacity", 0.4)
        .attr("stroke-width", 3);

      // Labels for larger nodes
      node
        .filter(
          (d) => d.mention_count >= maxMentions * 0.15 || nodes.length < 30,
        )
        .append("text")
        .text((d) =>
          d.name.length > 18 ? d.name.slice(0, 17) + "\u2026" : d.name,
        )
        .attr("text-anchor", "middle")
        .attr("dy", (d) => radiusScale(d.mention_count) + 14)
        .attr("font-size", "9px")
        .attr("fill", "var(--color-muted-foreground)")
        .attr("pointer-events", "none");

      // Hover tooltip
      node
        .append("title")
        .text(
          (d) => `${d.name}\nType: ${d.type}\nMentions: ${d.mention_count}`,
        );

      // Hover highlight
      node
        .on("mouseenter", function (_event, d) {
          select(this)
            .select("circle")
            .attr("stroke-width", 5)
            .attr("stroke-opacity", 0.8);
          link
            .attr("stroke-opacity", (l) =>
              (l.source as GraphNode).name === d.name ||
              (l.target as GraphNode).name === d.name
                ? 1
                : 0.1,
            )
            .attr("stroke", (l) =>
              (l.source as GraphNode).name === d.name ||
              (l.target as GraphNode).name === d.name
                ? entityColor(d.type)
                : "var(--color-border)",
            );
        })
        .on("mouseleave", function () {
          select(this)
            .select("circle")
            .attr("stroke-width", 3)
            .attr("stroke-opacity", 0.4);
          link.attr("stroke-opacity", 0.5).attr("stroke", "var(--color-border)");
        });

      // Click to navigate
      node.on("click", (_event, d) => {
        navigate({ to: "/entities/$id", params: { id: d.id } });
      });

      // Right-click context menu
      if (onNodeContextMenu) {
        node.on("contextmenu", (event: MouseEvent, d) => {
          onNodeContextMenu(event, { name: d.name, type: d.type });
        });
      }

      // Tick
      simulation.on("tick", () => {
        link
          .attr("x1", (d) => (d.source as GraphNode).x ?? 0)
          .attr("y1", (d) => (d.source as GraphNode).y ?? 0)
          .attr("x2", (d) => (d.target as GraphNode).x ?? 0)
          .attr("y2", (d) => (d.target as GraphNode).y ?? 0);

        node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
      });

      // Store refs for the filter effect
      simulationRef.current = simulation;
      nodeSelRef.current = node;
      linkSelRef.current = link;

      // Apply persisted type filter immediately (the filter effect won't
      // re-run if activeTypes hasn't changed since mount)
      const at = activeTypesRef.current;
      node.style("display", (d) =>
        at.has(d.type) || !ENTITY_COLORS[d.type] ? null : "none",
      );
      const visibleNames = new Set<string>();
      node.each((d) => {
        if (at.has(d.type) || !ENTITY_COLORS[d.type]) visibleNames.add(d.name);
      });
      link.style("display", (d) => {
        const src = (d.source as GraphNode).name;
        const tgt = (d.target as GraphNode).name;
        return visibleNames.has(src) && visibleNames.has(tgt) ? null : "none";
      });

      return () => {
        simulation.stop();
        simulationRef.current = null;
        nodeSelRef.current = null;
        linkSelRef.current = null;
      };
    }, [entities, connections, navigate, containerWidth, containerHeight, onNodeContextMenu]);

    // Filter effect: toggle node/link visibility when activeTypes changes
    // This avoids rebuilding the simulation and re-randomizing positions
    useEffect(() => {
      const nodeSel = nodeSelRef.current;
      const linkSel = linkSelRef.current;
      if (!nodeSel || !linkSel) return;

      // Show/hide nodes based on active types
      nodeSel.style("display", (d) =>
        activeTypes.has(d.type) || !ENTITY_COLORS[d.type] ? null : "none",
      );

      // Build set of visible node names for link filtering
      const visibleNames = new Set<string>();
      nodeSel.each((d) => {
        if (activeTypes.has(d.type) || !ENTITY_COLORS[d.type]) {
          visibleNames.add(d.name);
        }
      });

      // Show/hide links where both endpoints are visible
      linkSel.style("display", (d) => {
        const src = (d.source as GraphNode).name;
        const tgt = (d.target as GraphNode).name;
        return visibleNames.has(src) && visibleNames.has(tgt) ? null : "none";
      });
    }, [activeTypes]);

    return (
      <div ref={containerRef} className="w-full min-h-[300px] h-[calc(100vh-220px)]">
        <svg
          ref={svgRef}
          className="w-full h-full rounded-md border bg-background"
        />
      </div>
    );
  },
);
