import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { select } from "d3-selection";
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide, type SimulationNodeDatum, type SimulationLinkDatum, type Simulation } from "d3-force";
import { drag } from "d3-drag";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { entityColor } from "@/lib/colors";
import { useContainerSize } from "@/hooks/use-container-size";
import type { EntityResponse, EntityConnection } from "@/types";

interface GraphNode extends SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  isCenter: boolean;
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  relationship_type: string;
  weight: number;
}

interface ConnectionsGraphProps {
  entity: EntityResponse;
  connections: EntityConnection[];
  selectedConnection?: EntityConnection | null;
  onConnectionSelect?: (connection: EntityConnection | null) => void;
}

export function ConnectionsGraph({ entity, connections, selectedConnection, onConnectionSelect }: ConnectionsGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<Simulation<GraphNode, GraphLink> | null>(null);
  const navigate = useNavigate();
  const { ref: containerRef, width: containerWidth, height: containerHeight } = useContainerSize();

  // Data effect: rebuild simulation when entity/connections change
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || connections.length === 0 || containerWidth === 0 || containerHeight === 0) return;

    const width = containerWidth;
    const height = containerHeight;

    // Build nodes from connections
    const nodeMap = new Map<string, GraphNode>();
    nodeMap.set(entity.name, {
      id: entity.id,
      name: entity.name,
      type: entity.type,
      isCenter: true,
    });

    for (const conn of connections) {
      if (!nodeMap.has(conn.source)) {
        nodeMap.set(conn.source, {
          id: conn.source,
          name: conn.source,
          type: "DEFAULT",
          isCenter: false,
        });
      }
      if (!nodeMap.has(conn.target)) {
        nodeMap.set(conn.target, {
          id: conn.target,
          name: conn.target,
          type: conn.target_type ?? "DEFAULT",
          isCenter: false,
        });
      }
    }

    const nodes = Array.from(nodeMap.values());
    const links: GraphLink[] = connections.map((c) => ({
      source: c.source,
      target: c.target,
      relationship_type: c.relationship_type,
      weight: c.weight,
    }));

    // Clear previous render
    const sel = select(svg);
    sel.selectAll("*").remove();

    const g = sel
      .attr("width", width)
      .attr("height", height)
      .append("g");

    const simulation = forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.name)
          .distance(100),
      )
      .force("charge", forceManyBody().strength(-200))
      .force("center", forceCenter(width / 2, height / 2))
      .force("collide", forceCollide(30));

    const link = g
      .selectAll<SVGLineElement, GraphLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "var(--color-border)")
      .attr("stroke-opacity", 0.6)
      .attr("stroke-width", (d) => Math.max(1, Math.min(d.weight, 4)));

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

    node
      .append("circle")
      .attr("r", (d) => (d.isCenter ? 16 : 10))
      .attr("fill", (d) => entityColor(d.type))
      .attr("stroke", "var(--color-background)")
      .attr("stroke-width", 1.5);

    node
      .append("text")
      .text((d) => d.name)
      .attr("text-anchor", "middle")
      .attr("dy", (d) => (d.isCenter ? 28 : 22))
      .attr("font-size", "10px")
      .attr("fill", "var(--color-muted-foreground)")
      .attr("pointer-events", "none");

    // Click to select connection, double-click to navigate
    let clickTimer: ReturnType<typeof setTimeout> | null = null;
    node.on("click", (_event, d) => {
      if (d.isCenter) {
        onConnectionSelect?.(null);
        return;
      }
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
        // Double-click: navigate
        navigate({ to: "/entities/$id", params: { id: d.id } });
        return;
      }
      clickTimer = setTimeout(() => {
        clickTimer = null;
        // Single click: select connection
        const conn = connections.find(
          (c) => c.target === d.name || c.source === d.name,
        );
        if (conn) onConnectionSelect?.(conn);
      }, 250);
    });

    // Click background to deselect
    sel.on("click", (event) => {
      if (event.target === svg) onConnectionSelect?.(null);
    });

    // Tooltip on hover
    node.append("title").text((d) => `${d.name} (${d.type})\nClick to select, double-click to open`);

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as GraphNode).x ?? 0)
        .attr("y1", (d) => (d.source as GraphNode).y ?? 0)
        .attr("x2", (d) => (d.target as GraphNode).x ?? 0)
        .attr("y2", (d) => (d.target as GraphNode).y ?? 0);

      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
      simulationRef.current = null;
    };
  }, [entity, connections, navigate, containerWidth, containerHeight, onConnectionSelect]);

  // Highlight effect when selectedConnection changes
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const sel = select(svg);

    if (!selectedConnection) {
      // Reset all to default
      sel.selectAll("line")
        .attr("stroke", "var(--color-border)")
        .attr("stroke-opacity", 0.6)
        .attr("stroke-width", (d: unknown) => Math.max(1, Math.min((d as GraphLink).weight, 4)));
      sel.selectAll("circle")
        .attr("stroke", "var(--color-background)")
        .attr("stroke-width", 1.5);
      return;
    }

    const target = selectedConnection.target;
    const source = selectedConnection.source;

    // Dim all links, highlight selected
    sel.selectAll<SVGLineElement, GraphLink>("line")
      .attr("stroke", (d) => {
        const s = (d.source as GraphNode).name;
        const t = (d.target as GraphNode).name;
        return (s === source && t === target) || (s === target && t === source)
          ? "var(--color-primary)"
          : "var(--color-border)";
      })
      .attr("stroke-opacity", (d) => {
        const s = (d.source as GraphNode).name;
        const t = (d.target as GraphNode).name;
        return (s === source && t === target) || (s === target && t === source) ? 1 : 0.15;
      })
      .attr("stroke-width", (d) => {
        const s = (d.source as GraphNode).name;
        const t = (d.target as GraphNode).name;
        return (s === source && t === target) || (s === target && t === source)
          ? Math.max(2, Math.min(d.weight + 1, 6))
          : Math.max(1, Math.min(d.weight, 4));
      });

    // Highlight connected nodes
    sel.selectAll<SVGCircleElement, GraphNode>("circle")
      .attr("stroke", (d) =>
        d.name === target || d.name === source ? "var(--color-primary)" : "var(--color-background)",
      )
      .attr("stroke-width", (d) =>
        d.name === target || d.name === source ? 3 : 1.5,
      );
  }, [selectedConnection]);

  if (connections.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Connections</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No connections found for this entity.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          Connections ({connections.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div ref={containerRef} className="w-full min-h-[300px] h-[350px]">
          <svg
            ref={svgRef}
            className="w-full h-full"
          />
        </div>
      </CardContent>
    </Card>
  );
}
