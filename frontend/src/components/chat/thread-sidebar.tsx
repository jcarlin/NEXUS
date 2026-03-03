import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { Plus, MessageSquare, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { truncate, formatDate } from "@/lib/utils";
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

export function ThreadSidebar() {
  const params = useParams({ strict: false });
  const activeThreadId = "threadId" in params ? params.threadId : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["chat-threads"],
    queryFn: () =>
      apiClient<{ threads: ChatThread[] }>({
        url: "/api/v1/chats",
        method: "GET",
      }),
    refetchInterval: 30_000,
  });

  const threads = data?.threads ?? [];

  return (
    <div className="flex h-full w-64 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between border-b px-3 py-3">
        <span className="text-sm font-semibold">Threads</span>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/chat">
            <Plus className="mr-1 h-3.5 w-3.5" />
            New
          </Link>
        </Button>
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
          {groupByTime(threads).map((group) => (
            <div key={group.label}>
              <p className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                {group.label}
              </p>
              {group.threads.map((thread) => (
                <Link
                  key={thread.thread_id}
                  to="/chat/$threadId"
                  params={{ threadId: thread.thread_id }}
                  className={cn(
                    "flex flex-col gap-0.5 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent",
                    activeThreadId === thread.thread_id && "bg-accent",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate font-medium">
                      {truncate(thread.first_query, 40)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between pl-5.5 text-xs text-muted-foreground">
                    <span>{thread.message_count} messages</span>
                    <span>{formatDate(thread.last_message_at)}</span>
                  </div>
                </Link>
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
