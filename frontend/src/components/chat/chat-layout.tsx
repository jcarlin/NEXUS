import type { ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { ThreadSidebar } from "./thread-sidebar";
import { CitationSidebar } from "./citation-sidebar";
import { useCitationStore } from "@/stores/citation-store";
import { useAppStore } from "@/stores/app-store";

interface ChatLayoutProps {
  children: ReactNode;
}

export function ChatLayout({ children }: ChatLayoutProps) {
  const citationOpen = useCitationStore((s) => s.isOpen);
  const collapsed = useAppStore((s) => s.threadSidebarCollapsed);
  const toggle = useAppStore((s) => s.toggleThreadSidebar);

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] overflow-hidden">
      <div
        style={{ width: collapsed ? 48 : 260 }}
        className="shrink-0 transition-all duration-200"
      >
        <ThreadSidebar collapsed={collapsed} onToggle={toggle} />
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1">
        <ResizablePanel minSize={35}>
          {children}
        </ResizablePanel>

        {citationOpen && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={28} minSize={20} maxSize={45}>
              <CitationSidebar />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </div>
  );
}
