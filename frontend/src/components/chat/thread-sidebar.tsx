import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { Plus, MessageSquare, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { truncate, formatDate } from "@/lib/utils";
import type { ChatThread } from "@/types";

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

        <div className="space-y-0.5 p-2">
          {threads.map((thread) => (
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
      </ScrollArea>
    </div>
  );
}
