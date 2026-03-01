import { useEffect, useRef, useCallback, useImperativeHandle, forwardRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import * as d3 from "d3";
import type { EntityResponse, EntityConnection } from "@/types";

const TYPE_COLORS: Record<string, string> = {
  PERSON: "#60a5fa",
  ORG: "#34d399",
  LOCATION: "#fb923c",
  DATE: "#a78bfa",
  MONEY: "#f472b6",
  DEFAULT: "#94a3b8",
};

function nodeColor(type: string): string {
  return TYPE_COLORS[type] ?? TYPE_COLORS["DEFAULT"]!;
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  mention_count: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
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
}

export const NetworkGraph = forwardRef<NetworkGraphHandle, NetworkGraphProps>(
  function NetworkGraph({ entities, connections, activeTypes }, ref) {
    const svgRef = useRef<SVGSVGElement>(null);
    const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
    const navigate = useNavigate({});

    const zoomIn = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      d3.select(svg)
        .transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 1.4);
    }, []);

    const zoomOut = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      d3.select(svg)
        .transition()
        .duration(300)
        .call(zoomRef.current.scaleBy, 0.7);
    }, []);

    const fitView = useCallback(() => {
      const svg = svgRef.current;
      if (!svg || !zoomRef.current) return;
      d3.select(svg)
        .transition()
        .duration(500)
        .call(zoomRef.current.transform, d3.zoomIdentity);
    }, []);

    useImperativeHandle(ref, () => ({ zoomIn, zoomOut, fitView }), [
      zoomIn,
      zoomOut,
      fitView,
    ]);

    useEffect(() => {
      const svg = svgRef.current;
      if (!svg) return;

      const width = svg.clientWidth || 900;
      const height = svg.clientHeight || 600;

      // Filter entities by active types
      const filteredEntities = entities.filter(
        (e) => activeTypes.has(e.type) || !TYPE_COLORS[e.type],
      );
      const entityNames = new Set(filteredEntities.map((e) => e.name));

      // Build node map from entities
      const nodeMap = new Map<string, GraphNode>();
      for (const e of filteredEntities) {
        nodeMap.set(e.name, {
          id: e.id,
          name: e.name,
          type: e.type,
          mention_count: e.mention_count,
        });
      }

      // Filter connections where both endpoints are in visible nodes
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
      const sel = d3.select(svg);
      sel.selectAll("*").remove();

      // Size scale for nodes
      const maxMentions = Math.max(...nodes.map((n) => n.mention_count), 1);
      const radiusScale = d3
        .scaleSqrt()
        .domain([0, maxMentions])
        .range([5, 24]);

      // Zoom behavior
      const zoom = d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 8])
        .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
          g.attr("transform", event.transform.toString());
        });
      zoomRef.current = zoom;
      sel.attr("width", width).attr("height", height).call(zoom);

      const g = sel.append("g");

      // Simulation
      const simulation = d3
        .forceSimulation<GraphNode>(nodes)
        .force(
          "link",
          d3
            .forceLink<GraphNode, GraphLink>(links)
            .id((d) => d.name)
            .distance(120),
        )
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force(
          "collide",
          d3.forceCollide<GraphNode>((d) => radiusScale(d.mention_count) + 4),
        );

      // Links
      const link = g
        .selectAll<SVGLineElement, GraphLink>("line")
        .data(links)
        .join("line")
        .attr("stroke", "#525252")
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
          d3
            .drag<SVGGElement, GraphNode>()
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
        .attr("fill", (d) => nodeColor(d.type))
        .attr("fill-opacity", 0.85)
        .attr("stroke", (d) => nodeColor(d.type))
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
        .attr("fill", "#a1a1aa")
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
          d3.select(this)
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
                ? nodeColor(d.type)
                : "#525252",
            );
        })
        .on("mouseleave", function () {
          d3.select(this)
            .select("circle")
            .attr("stroke-width", 3)
            .attr("stroke-opacity", 0.4);
          link.attr("stroke-opacity", 0.5).attr("stroke", "#525252");
        });

      // Click to navigate
      node.on("click", (_event, d) => {
        navigate({ to: "/entities/$id", params: { id: d.id } });
      });

      // Tick
      simulation.on("tick", () => {
        link
          .attr("x1", (d) => (d.source as GraphNode).x ?? 0)
          .attr("y1", (d) => (d.source as GraphNode).y ?? 0)
          .attr("x2", (d) => (d.target as GraphNode).x ?? 0)
          .attr("y2", (d) => (d.target as GraphNode).y ?? 0);

        node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
      });

      return () => {
        simulation.stop();
      };
    }, [entities, connections, activeTypes, navigate]);

    return (
      <svg
        ref={svgRef}
        className="w-full rounded-md border bg-background"
        style={{ height: "calc(100vh - 220px)", minHeight: 400 }}
      />
    );
  },
);
