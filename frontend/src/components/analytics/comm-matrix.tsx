import { useMemo } from "react";
import { scaleSequential } from "d3-scale";
import { interpolateYlOrRd } from "d3-scale-chromatic";
import { Skeleton } from "@/components/ui/skeleton";
import { useContainerSize } from "@/hooks/use-container-size";

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

const LABEL_WIDTH = 120;
const LABEL_HEIGHT = 120;
const MIN_CELL_SIZE = 20;
const MAX_CELL_SIZE = 60;

export function CommMatrix({ matrix, entities, loading, onCellClick }: CommMatrixProps) {
  const { ref: containerRef, width: containerWidth } = useContainerSize();

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
    () => scaleSequential(interpolateYlOrRd).domain([0, maxCount || 1]),
    [maxCount],
  );

  const cellSize = useMemo(() => {
    if (containerWidth === 0 || entities.length === 0) return 40;
    const available = containerWidth - LABEL_WIDTH;
    return Math.min(MAX_CELL_SIZE, Math.max(MIN_CELL_SIZE, Math.floor(available / entities.length)));
  }, [containerWidth, entities.length]);

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

  const width = LABEL_WIDTH + entities.length * cellSize;
  const height = LABEL_HEIGHT + entities.length * cellSize;

  return (
    <div ref={containerRef} className="overflow-auto rounded-md border">
      <svg width={width} height={height}>
        {/* Column labels (receivers) */}
        {entities.map((entity, i) => (
          <text
            key={`col-${entity}`}
            x={LABEL_WIDTH + i * cellSize + cellSize / 2}
            y={LABEL_HEIGHT - 6}
            textAnchor="end"
            fontSize={10}
            fill="currentColor"
            className="text-muted-foreground"
            transform={`rotate(-45, ${LABEL_WIDTH + i * cellSize + cellSize / 2}, ${LABEL_HEIGHT - 6})`}
          >
            {entity.length > 15 ? entity.slice(0, 14) + "\u2026" : entity}
          </text>
        ))}

        {/* Row labels (senders) + cells */}
        {entities.map((sender, row) => (
          <g key={`row-${sender}`}>
            <text
              x={LABEL_WIDTH - 6}
              y={LABEL_HEIGHT + row * cellSize + cellSize / 2 + 4}
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
                    x={LABEL_WIDTH + col * cellSize}
                    y={LABEL_HEIGHT + row * cellSize}
                    width={cellSize - 1}
                    height={cellSize - 1}
                    fill={count > 0 ? colorScale(count) : "var(--color-muted)"}
                    rx={2}
                    className="cursor-pointer"
                    onClick={() => onCellClick?.(sender, receiver)}
                  >
                    <title>{`${sender} → ${receiver}: ${count}`}</title>
                  </rect>
                  {count > 0 && cellSize >= 30 && (
                    <text
                      x={LABEL_WIDTH + col * cellSize + cellSize / 2 - 0.5}
                      y={LABEL_HEIGHT + row * cellSize + cellSize / 2 + 4}
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
