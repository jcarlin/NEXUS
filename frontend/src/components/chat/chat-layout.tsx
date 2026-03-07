import { useCallback, useEffect, useRef, type ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { useGroupRef } from "react-resizable-panels";
import { ThreadSidebar } from "./thread-sidebar";
import { CitationSidebar } from "./citation-sidebar";
import { useCitationStore } from "@/stores/citation-store";
import { useAppStore } from "@/stores/app-store";

import type { PanelSize } from "react-resizable-panels";

interface ChatLayoutProps {
  children: ReactNode;
}

export function ChatLayout({ children }: ChatLayoutProps) {
  const citationOpen = useCitationStore((s) => s.isOpen);
  const collapsed = useAppStore((s) => s.threadSidebarCollapsed);
  const toggle = useAppStore((s) => s.toggleThreadSidebar);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);
  const setThreadSidebarCollapsed = useAppStore((s) => s.setThreadSidebarCollapsed);

  const prevSidebarState = useRef<{ sidebar: boolean; threadSidebar: boolean } | null>(null);
  const groupRef = useGroupRef();

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

  // Programmatically set panel layout when citationOpen changes
  useEffect(() => {
    if (citationOpen) {
      groupRef.current?.setLayout({ "chat-main": 60, "citation-sidebar": 40 });
    } else {
      groupRef.current?.setLayout({ "chat-main": 100, "citation-sidebar": 0 });
    }
  }, [citationOpen, groupRef]);

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
        style={{ width: collapsed ? 48 : 260 }}
        className="shrink-0 transition-all duration-200"
      >
        <ThreadSidebar collapsed={collapsed} onToggle={toggle} />
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1" groupRef={groupRef}>
        <ResizablePanel id="chat-main" minSize={35}>
          {children}
        </ResizablePanel>

        <ResizableHandle
          withHandle={citationOpen}
          disabled={!citationOpen}
          className={!citationOpen ? "w-0 opacity-0" : ""}
        />
        <ResizablePanel
          id="citation-sidebar"
          defaultSize={0}
          collapsible
          collapsedSize={0}
          minSize={20}
          maxSize={50}
          onResize={handleCitationResize}
        >
          {citationOpen && <CitationSidebar />}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
