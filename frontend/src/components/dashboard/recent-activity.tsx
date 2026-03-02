import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatDateTime } from "@/lib/utils";
import type { AuditLogEntry, PaginatedResponse } from "@/types";

export function RecentActivity() {
  const matterId = useAppStore((s) => s.matterId);

  const { data, isLoading } = useQuery({
    queryKey: ["recent-activity", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<AuditLogEntry>>({
        url: "/api/v1/admin/audit-log",
        method: "GET",
        params: { limit: 10 },
      }),
    enabled: !!matterId,
    refetchInterval: 30_000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Recent Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[280px]">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {data?.items.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {entry.action}
                    </Badge>
                    <span className="text-muted-foreground">{entry.resource_type ?? entry.resource}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</span>
                </div>
              ))}
              {data?.items.length === 0 && (
                <p className="text-center text-sm text-muted-foreground py-8">No recent activity</p>
              )}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
