import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { Plus, MessageSquare, Loader2, ChevronsLeft } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, formatDate } from "@/lib/utils";
import type { ChatThread } from "@/types";

function groupByTime(threads: ChatThread[]): { label: string; threads: ChatThread[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups = {
    Today: [] as ChatThread[],
    Yesterday: [] as ChatThread[],
    "This Week": [] as ChatThread[],
    Older: [] as ChatThread[],
  };

  for (const t of threads) {
    const d = new Date(t.last_message_at);
    if (d >= today) groups.Today.push(t);
    else if (d >= yesterday) groups.Yesterday.push(t);
    else if (d >= weekAgo) groups["This Week"].push(t);
    else groups.Older.push(t);
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, threads: items }));
}

function ThreadItem({ thread, isActive, onSelect }: { thread: ChatThread; isActive: boolean; onSelect?: () => void }) {
  return (
    <Link
      to="/chat/$threadId"
      params={{ threadId: thread.thread_id }}
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-0.5 overflow-hidden rounded-md px-3 py-2 text-xs transition-colors hover:bg-accent",
        isActive && "bg-accent",
      )}
    >
      <div className="flex items-start gap-2 overflow-hidden">
        <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="line-clamp-2 font-medium">
          {thread.first_query}
        </span>
      </div>
      <div className="flex items-center justify-between pl-5.5 text-[11px] text-muted-foreground">
        <span>{thread.message_count} messages</span>
        <span>{formatDate(thread.last_message_at)}</span>
      </div>
    </Link>
  );
}

interface ThreadSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  onThreadSelect?: () => void;
}

export function ThreadSidebar({ collapsed, onToggle, onThreadSelect }: ThreadSidebarProps) {
  const matterId = useAppStore((s) => s.matterId);
  const params = useParams({ strict: false });
  const activeThreadId = "threadId" in params ? params.threadId : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["chat-threads", matterId],
    queryFn: () =>
      apiClient<{ threads: ChatThread[] }>({
        url: "/api/v1/chats",
        method: "GET",
      }),
    refetchInterval: 30_000,
  });

  const threads = data?.threads ?? [];

  if (collapsed) {
    return (
      <div className="flex h-full w-full flex-col items-center border-r bg-muted/30 pt-2 gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
              <Link to="/chat" onClick={onThreadSelect}>
                <Plus className="h-4 w-4" />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">New chat</TooltipContent>
        </Tooltip>
        <button
          type="button"
          className="flex flex-1 w-full flex-col items-center justify-start gap-3 pt-2 cursor-pointer hover:bg-muted/50 transition-colors rounded-md"
          onClick={onToggle}
          aria-label="Expand chat history"
        >
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <span className="text-[10px] font-medium tracking-wide text-muted-foreground [writing-mode:vertical-lr]">
            History
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between border-b px-3 py-3">
        <span className="text-sm font-semibold">Chat History</span>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/chat" onClick={onThreadSelect}>
              <Plus className="mr-1 h-3.5 w-3.5" />
              New
            </Link>
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onToggle}>
            <ChevronsLeft className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}

        {!isLoading && threads.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            No conversations yet
          </p>
        )}

        <div className="p-2">
          {/* Active thread pinned at top */}
          {activeThreadId && threads.find((t) => t.thread_id === activeThreadId) && (
            <>
              <ThreadItem
                thread={threads.find((t) => t.thread_id === activeThreadId)!}
                isActive
                onSelect={onThreadSelect}
              />
              <div className="mx-3 my-1.5 border-b border-border/50" />
            </>
          )}

          {/* Remaining threads grouped by time */}
          {groupByTime(threads.filter((t) => t.thread_id !== activeThreadId)).map((group) => (
            <div key={group.label}>
              <p className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                {group.label}
              </p>
              {group.threads.map((thread) => (
                <ThreadItem
                  key={thread.thread_id}
                  thread={thread}
                  isActive={false}
                  onSelect={onThreadSelect}
                />
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
