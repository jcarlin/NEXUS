import { useState, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import type { Annotation, AnnotationAnchor } from "@/types";

const TYPE_COLORS: Record<string, string> = {
  highlight: "rgba(255, 230, 0, 0.3)",
  note: "rgba(59, 130, 246, 0.25)",
  tag: "rgba(16, 185, 129, 0.25)",
};

interface AnnotationLayerProps {
  pageNumber: number;
  annotations: Annotation[];
  selectedId?: string | null;
  onAnnotationClick?: (annotation: Annotation) => void;
  onCreateHighlight?: (anchor: AnnotationAnchor, pageNumber: number) => void;
}

export function AnnotationLayer({
  pageNumber,
  annotations,
  selectedId,
  onAnnotationClick,
  onCreateHighlight,
}: AnnotationLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);

  const pageAnnotations = annotations.filter((a) => a.page_number === pageNumber);

  const toPercent = useCallback(
    (clientX: number, clientY: number) => {
      const el = containerRef.current;
      if (!el) return { x: 0, y: 0 };
      const rect = el.getBoundingClientRect();
      return {
        x: ((clientX - rect.left) / rect.width) * 100,
        y: ((clientY - rect.top) / rect.height) * 100,
      };
    },
    [],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!onCreateHighlight) return;
      // Only start drag on left-click on the empty area
      if (e.button !== 0) return;
      const pos = toPercent(e.clientX, e.clientY);
      setDragStart(pos);
      setDragCurrent(pos);
    },
    [onCreateHighlight, toPercent],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragStart) return;
      setDragCurrent(toPercent(e.clientX, e.clientY));
    },
    [dragStart, toPercent],
  );

  const handleMouseUp = useCallback(() => {
    if (!dragStart || !dragCurrent || !onCreateHighlight) {
      setDragStart(null);
      setDragCurrent(null);
      return;
    }

    const x = Math.min(dragStart.x, dragCurrent.x);
    const y = Math.min(dragStart.y, dragCurrent.y);
    const width = Math.abs(dragCurrent.x - dragStart.x);
    const height = Math.abs(dragCurrent.y - dragStart.y);

    // Only create if the selection is big enough (> 1% in both dimensions)
    if (width > 1 && height > 1) {
      onCreateHighlight({ x, y, width, height }, pageNumber);
    }

    setDragStart(null);
    setDragCurrent(null);
  }, [dragStart, dragCurrent, onCreateHighlight, pageNumber]);

  // Compute drag selection rectangle
  const dragRect =
    dragStart && dragCurrent
      ? {
          left: `${Math.min(dragStart.x, dragCurrent.x)}%`,
          top: `${Math.min(dragStart.y, dragCurrent.y)}%`,
          width: `${Math.abs(dragCurrent.x - dragStart.x)}%`,
          height: `${Math.abs(dragCurrent.y - dragStart.y)}%`,
        }
      : null;

  return (
    <div
      ref={containerRef}
      data-testid="annotation-layer"
      className={cn("absolute inset-0", onCreateHighlight ? "pointer-events-auto" : "pointer-events-none")}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      {pageAnnotations.map((annotation) => {
        const anchor = annotation.anchor as AnnotationAnchor | Record<string, never>;
        if (!anchor || !("x" in anchor)) return null;
        const a = anchor as AnnotationAnchor;

        const isSelected = annotation.id === selectedId;
        const bgColor = annotation.color ?? TYPE_COLORS[annotation.annotation_type] ?? TYPE_COLORS.note;

        return (
          <div
            key={annotation.id}
            data-testid="annotation-rect"
            className={cn("absolute cursor-pointer pointer-events-auto rounded-sm", isSelected && "ring-2 ring-primary")}
            style={{
              left: `${a.x}%`,
              top: `${a.y}%`,
              width: `${a.width}%`,
              height: `${a.height}%`,
              backgroundColor: bgColor,
              border: isSelected ? undefined : "1px solid rgba(0,0,0,0.1)",
            }}
            onClick={(e) => {
              e.stopPropagation();
              onAnnotationClick?.(annotation);
            }}
            title={annotation.content}
          />
        );
      })}

      {/* Drag selection preview */}
      {dragRect && (
        <div
          className="absolute rounded-sm pointer-events-none border-2 border-dashed border-primary bg-primary/15"
          style={dragRect}
        />
      )}
    </div>
  );
}
