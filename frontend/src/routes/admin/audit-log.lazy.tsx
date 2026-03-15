import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { AuditLogEntry, PaginatedResponse } from "@/types";
import { AuditLogTable } from "@/components/admin/audit-log-table";

export const Route = createLazyFileRoute("/admin/audit-log")({
  component: AuditLogPage,
});

function AuditLogPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-audit-log"],
    queryFn: () =>
      apiClient<PaginatedResponse<AuditLogEntry>>({
        url: "/api/v1/admin/audit-log",
        method: "GET",
        params: { limit: 50, offset: 0 },
      }),
  });

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
        <p className="text-muted-foreground">
          Review platform activity and API audit trail.
        </p>
      </div>

      <AuditLogTable data={data?.items ?? []} isLoading={isLoading} />
    </div>
  );
}
