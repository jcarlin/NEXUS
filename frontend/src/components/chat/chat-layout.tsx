import { useCallback, useEffect, useRef, type ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { usePanelRef } from "react-resizable-panels";
import { ChevronsLeft, ChevronsRight, Bug } from "lucide-react";
import { ThreadSidebar } from "./thread-sidebar";
import { CitationSidebar } from "./citation-sidebar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCitationStore } from "@/stores/citation-store";
import { useAppStore } from "@/stores/app-store";
import { useDevModeStore } from "@/stores/dev-mode-store";
import { cn } from "@/lib/utils";

import type { PanelSize } from "react-resizable-panels";

interface ChatLayoutProps {
  children: ReactNode;
}

export function ChatLayout({ children }: ChatLayoutProps) {
  const citationOpen = useCitationStore((s) => s.isOpen);
  const citationMode = useCitationStore((s) => s.mode);
  const hasSources = useCitationStore((s) => s.allSources.length > 0);
  const toggleCitation = useCitationStore((s) => s.toggle);
  const devMode = useDevModeStore((s) => s.enabled);
  const toggleDevMode = useDevModeStore((s) => s.toggle);
  const collapsed = useAppStore((s) => s.threadSidebarCollapsed);
  const toggle = useAppStore((s) => s.toggleThreadSidebar);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);
  const setThreadSidebarCollapsed = useAppStore((s) => s.setThreadSidebarCollapsed);

  const prevSidebarState = useRef<{ sidebar: boolean; threadSidebar: boolean } | null>(null);
  const citationPanelRef = usePanelRef();

  useEffect(() => {
    if (citationOpen) {
      // Snapshot current states before collapsing
      prevSidebarState.current = {
        sidebar: useAppStore.getState().sidebarCollapsed,
        threadSidebar: useAppStore.getState().threadSidebarCollapsed,
      };
      setSidebarCollapsed(true);
      setThreadSidebarCollapsed(true);
    } else if (prevSidebarState.current) {
      // Restore previous states
      setSidebarCollapsed(prevSidebarState.current.sidebar);
      setThreadSidebarCollapsed(prevSidebarState.current.threadSidebar);
      prevSidebarState.current = null;
    }
  }, [citationOpen, setSidebarCollapsed, setThreadSidebarCollapsed]);

  // Programmatically resize citation panel when citationOpen or mode changes
  useEffect(() => {
    if (citationOpen) {
      const size = citationMode === "expanded" ? "65%" : "40%";
      citationPanelRef.current?.resize(size);
    } else {
      citationPanelRef.current?.collapse();
    }
  }, [citationOpen, citationMode, citationPanelRef]);

  // Sync drag-to-collapse with store: when user drags panel below minSize, it auto-collapses to 0%
  const handleCitationResize = useCallback(
    (size: PanelSize, _id: string | number | undefined, prevSize: PanelSize | undefined) => {
      if (prevSize && prevSize.asPercentage > 0 && size.asPercentage === 0) {
        useCitationStore.getState().toggle();
      }
    },
    [],
  );

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] overflow-hidden">
      <div
        className={`shrink-0 transition-all duration-200 hidden md:block ${collapsed ? "w-12" : "w-[260px]"}`}
      >
        <ThreadSidebar collapsed={collapsed} onToggle={toggle} />
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1">
        <ResizablePanel id="chat-main" minSize="35%">
          <div className="relative h-full">
            <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn("h-7 w-7", devMode && "text-primary bg-primary/10")}
                    onClick={toggleDevMode}
                    aria-label="Toggle dev trace mode"
                  >
                    <Bug className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {devMode ? "Disable trace panel" : "Enable trace panel"}
                </TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={toggleCitation}
                    disabled={!citationOpen && !hasSources}
                    aria-label="Toggle citation sidebar"
                  >
                    {citationOpen ? (
                      <ChevronsRight className="h-4 w-4" />
                    ) : (
                      <ChevronsLeft className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {citationOpen ? "Close citations" : "Open citations"}
                </TooltipContent>
              </Tooltip>
            </div>
            {children}
          </div>
        </ResizablePanel>

        <ResizableHandle
          withHandle={citationOpen}
          disabled={!citationOpen}
          className={!citationOpen ? "w-0 opacity-0" : ""}
        />
        <ResizablePanel
          id="citation-sidebar"
          defaultSize="0%"
          collapsible
          collapsedSize="0%"
          minSize={citationMode === "expanded" ? "40%" : "20%"}
          maxSize="75%"
          onResize={handleCitationResize}
          panelRef={citationPanelRef}
        >
          {citationOpen && <CitationSidebar />}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
