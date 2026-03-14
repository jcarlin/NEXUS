import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { entityColor } from "@/lib/colors";
import { useContainerSize } from "@/hooks/use-container-size";
import type { EntityResponse, EntityConnection } from "@/types";

interface GraphNode extends d3.SimulationNodeDatum {
  name: string;
  type: string;
  mention_count: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  weight: number;
}

interface MiniGraphProps {
  entities: EntityResponse[];
  connections: EntityConnection[];
}

export function MiniGraph({ entities, connections }: MiniGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { ref: containerRef, width, height } = useContainerSize();

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || width === 0 || height === 0 || entities.length === 0) return;

    const sel = d3.select(svg);
    sel.selectAll("*").remove();

    const entityNames = new Set(entities.map((e) => e.name));

    const nodes: GraphNode[] = entities.map((e) => ({
      name: e.name,
      type: e.type,
      mention_count: e.mention_count,
    }));

    const links: GraphLink[] = connections
      .filter((c) => entityNames.has(c.source) && entityNames.has(c.target))
      .map((c) => ({
        source: c.source,
        target: c.target,
        weight: c.weight,
      }));

    const maxMentions = Math.max(...nodes.map((n) => n.mention_count), 1);
    const radiusScale = d3
      .scaleSqrt()
      .domain([0, maxMentions])
      .range([3, 12]);

    sel.attr("width", width).attr("height", height);

    const g = sel.append("g");

    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.name)
          .distance(60),
      )
      .force("charge", d3.forceManyBody().strength(-150))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collide",
        d3.forceCollide<GraphNode>((d) => radiusScale(d.mention_count) + 2),
      );

    const link = g
      .selectAll<SVGLineElement, GraphLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "var(--color-border)")
      .attr("stroke-opacity", 0.4)
      .attr("stroke-width", (d) => Math.max(0.5, Math.min(d.weight, 3)));

    const node = g
      .selectAll<SVGCircleElement, GraphNode>("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => radiusScale(d.mention_count))
      .attr("fill", (d) => entityColor(d.type))
      .attr("fill-opacity", 0.85)
      .attr("stroke", (d) => entityColor(d.type))
      .attr("stroke-opacity", 0.3)
      .attr("stroke-width", 2);

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as GraphNode).x ?? 0)
        .attr("y1", (d) => (d.source as GraphNode).y ?? 0)
        .attr("x2", (d) => (d.target as GraphNode).x ?? 0)
        .attr("y2", (d) => (d.target as GraphNode).y ?? 0);

      node.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
    });

    return () => {
      simulation.stop();
    };
  }, [entities, connections, width, height]);

  return (
    <div ref={containerRef} className="h-[180px] w-full">
      <svg
        ref={svgRef}
        className="w-full h-full pointer-events-none"
      />
    </div>
  );
}
