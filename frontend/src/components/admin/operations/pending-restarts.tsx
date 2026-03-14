import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { apiClient } from "@/api/client";

interface FeatureFlagDetail {
  flag_name: string;
  display_name: string;
  risk_level: string;
  is_override: boolean;
}

export function PendingRestarts() {
  const { data } = useQuery({
    queryKey: ["admin-feature-flags"],
    queryFn: () =>
      apiClient<{ items: FeatureFlagDetail[] }>({
        url: "/api/v1/admin/feature-flags",
        method: "GET",
      }),
  });

  const pendingFlags = (data?.items ?? []).filter(
    (f) => f.risk_level === "restart" && f.is_override,
  );

  if (pendingFlags.length === 0) return null;

  const flagNames = pendingFlags.map((f) => f.display_name).join(", ");

  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950">
      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500 mt-0.5 shrink-0" />
      <p className="text-xs text-amber-800 dark:text-amber-200">
        <strong>Pending restarts:</strong> {flagNames} flag(s) changed. Restart
        the API server to apply.
      </p>
    </div>
  );
}
