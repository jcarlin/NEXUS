import { cn } from "@/lib/utils";

type DiffOp = "equal" | "insert" | "delete" | "replace";

interface DiffBlock {
  op: DiffOp;
  left_start: number | null;
  left_end: number | null;
  right_start: number | null;
  right_end: number | null;
  left_text: string;
  right_text: string;
}

interface DiffViewerProps {
  blocks: DiffBlock[];
  leftFilename: string;
  rightFilename: string;
  truncated?: boolean;
}

const OP_STYLES: Record<DiffOp, { left: string; right: string }> = {
  equal: { left: "", right: "" },
  insert: {
    left: "bg-transparent",
    right: "bg-green-100 dark:bg-green-950 border-l-2 border-green-500",
  },
  delete: {
    left: "bg-red-100 dark:bg-red-950 border-l-2 border-red-500",
    right: "bg-transparent",
  },
  replace: {
    left: "bg-amber-100 dark:bg-amber-950 border-l-2 border-amber-500",
    right: "bg-amber-100 dark:bg-amber-950 border-l-2 border-amber-500",
  },
};

export function DiffViewer({
  blocks,
  leftFilename,
  rightFilename,
  truncated = false,
}: DiffViewerProps) {
  return (
    <div className="flex flex-col gap-2">
      {truncated && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
          Documents were truncated to 50,000 characters for comparison. Some content may not be shown.
        </div>
      )}

      <div className="grid grid-cols-2 gap-0 overflow-hidden rounded-md border">
        {/* Header */}
        <div className="border-b border-r bg-muted/50 px-4 py-2 font-medium text-sm">
          {leftFilename}
        </div>
        <div className="border-b bg-muted/50 px-4 py-2 font-medium text-sm">
          {rightFilename}
        </div>

        {/* Diff blocks */}
        {blocks.map((block, idx) => (
          <DiffBlockRow key={idx} block={block} />
        ))}

        {blocks.length === 0 && (
          <>
            <div className="col-span-2 p-8 text-center text-muted-foreground text-sm">
              No differences found between the two documents.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function DiffBlockRow({ block }: { block: DiffBlock }) {
  const styles = OP_STYLES[block.op];

  return (
    <>
      <div
        className={cn(
          "whitespace-pre-wrap border-r px-4 py-1 font-mono text-xs leading-relaxed",
          styles.left,
        )}
      >
        {block.left_text || (block.op === "insert" ? "\u00a0" : "")}
      </div>
      <div
        className={cn(
          "whitespace-pre-wrap px-4 py-1 font-mono text-xs leading-relaxed",
          styles.right,
        )}
      >
        {block.right_text || (block.op === "delete" ? "\u00a0" : "")}
      </div>
    </>
  );
}
