import { useRef, useMemo } from "react";
import * as d3 from "d3";
import { Skeleton } from "@/components/ui/skeleton";

export interface MatrixEntry {
  sender: string;
  receiver: string;
  count: number;
}

interface CommMatrixProps {
  matrix: MatrixEntry[];
  entities: string[];
  loading?: boolean;
  onCellClick?: (sender: string, receiver: string) => void;
}

const CELL_SIZE = 40;
const LABEL_WIDTH = 120;
const LABEL_HEIGHT = 120;

export function CommMatrix({ matrix, entities, loading, onCellClick }: CommMatrixProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  const { countMap, maxCount } = useMemo(() => {
    const map = new Map<string, number>();
    let max = 0;
    for (const entry of matrix) {
      const key = `${entry.sender}|${entry.receiver}`;
      map.set(key, entry.count);
      if (entry.count > max) max = entry.count;
    }
    return { countMap: map, maxCount: max };
  }, [matrix]);

  const colorScale = useMemo(
    () => d3.scaleSequential(d3.interpolateYlOrRd).domain([0, maxCount || 1]),
    [maxCount],
  );

  if (loading) {
    return <Skeleton className="h-[400px] w-full" />;
  }

  if (entities.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No communication data available.
      </p>
    );
  }

  const width = LABEL_WIDTH + entities.length * CELL_SIZE;
  const height = LABEL_HEIGHT + entities.length * CELL_SIZE;

  return (
    <div className="overflow-auto rounded-md border">
      <svg ref={svgRef} width={width} height={height}>
        {/* Column labels (receivers) */}
        {entities.map((entity, i) => (
          <text
            key={`col-${entity}`}
            x={LABEL_WIDTH + i * CELL_SIZE + CELL_SIZE / 2}
            y={LABEL_HEIGHT - 6}
            textAnchor="end"
            fontSize={10}
            fill="currentColor"
            className="text-muted-foreground"
            transform={`rotate(-45, ${LABEL_WIDTH + i * CELL_SIZE + CELL_SIZE / 2}, ${LABEL_HEIGHT - 6})`}
          >
            {entity.length > 15 ? entity.slice(0, 14) + "\u2026" : entity}
          </text>
        ))}

        {/* Row labels (senders) + cells */}
        {entities.map((sender, row) => (
          <g key={`row-${sender}`}>
            <text
              x={LABEL_WIDTH - 6}
              y={LABEL_HEIGHT + row * CELL_SIZE + CELL_SIZE / 2 + 4}
              textAnchor="end"
              fontSize={10}
              fill="currentColor"
              className="text-muted-foreground"
            >
              {sender.length > 15 ? sender.slice(0, 14) + "\u2026" : sender}
            </text>

            {entities.map((receiver, col) => {
              const count = countMap.get(`${sender}|${receiver}`) ?? 0;
              return (
                <g key={`cell-${sender}-${receiver}`}>
                  <rect
                    x={LABEL_WIDTH + col * CELL_SIZE}
                    y={LABEL_HEIGHT + row * CELL_SIZE}
                    width={CELL_SIZE - 1}
                    height={CELL_SIZE - 1}
                    fill={count > 0 ? colorScale(count) : "var(--color-muted)"}
                    rx={2}
                    className="cursor-pointer"
                    onClick={() => onCellClick?.(sender, receiver)}
                  >
                    <title>{`${sender} → ${receiver}: ${count}`}</title>
                  </rect>
                  {count > 0 && CELL_SIZE >= 30 && (
                    <text
                      x={LABEL_WIDTH + col * CELL_SIZE + CELL_SIZE / 2 - 0.5}
                      y={LABEL_HEIGHT + row * CELL_SIZE + CELL_SIZE / 2 + 4}
                      textAnchor="middle"
                      fontSize={9}
                      fill={count > maxCount * 0.6 ? "white" : "black"}
                      pointerEvents="none"
                    >
                      {count}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}
