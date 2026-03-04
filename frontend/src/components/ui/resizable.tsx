import { GripVertical } from "lucide-react";
import {
  Group as PanelGroupPrimitive,
  Panel,
  Separator as PanelResizeHandlePrimitive,
} from "react-resizable-panels";

import { cn } from "@/lib/utils";

function ResizablePanelGroup({
  className,
  direction = "horizontal",
  ...props
}: Omit<React.ComponentProps<typeof PanelGroupPrimitive>, "orientation"> & {
  direction?: "horizontal" | "vertical";
}) {
  return (
    <PanelGroupPrimitive
      orientation={direction}
      className={cn("flex h-full w-full", className)}
      {...props}
    />
  );
}

const ResizablePanel = Panel;

function ResizableHandle({
  withHandle,
  className,
  ...props
}: React.ComponentProps<typeof PanelResizeHandlePrimitive> & {
  withHandle?: boolean;
}) {
  return (
    <PanelResizeHandlePrimitive
      className={cn(
        "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:-left-1 after:-right-1 after:content-[''] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 data-[separator=active]:bg-primary/50",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border bg-border">
          <GripVertical className="h-2.5 w-2.5" />
        </div>
      )}
    </PanelResizeHandlePrimitive>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
