import { PanelRight, PanelRightClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCitationStore } from "@/stores/citation-store";

export function ChatHeader() {
  const isOpen = useCitationStore((s) => s.isOpen);
  const hasSources = useCitationStore((s) => s.allSources.length > 0);
  const toggle = useCitationStore((s) => s.toggle);

  return (
    <div className="flex h-10 shrink-0 items-center justify-end border-b px-3">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={toggle}
            disabled={!isOpen && !hasSources}
            aria-label="Toggle citation sidebar"
          >
            {isOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRight className="h-4 w-4" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {isOpen ? "Close citations" : "Open citations"}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
