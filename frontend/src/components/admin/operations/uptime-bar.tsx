import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";

interface UptimeSummary {
  service_name: string;
  uptime_24h: number;
  uptime_7d: number;
  uptime_30d: number;
  total_checks_24h: number;
  total_checks_7d: number;
  total_checks_30d: number;
}

export function UptimeBar() {
  const { data } = useQuery({
    queryKey: ["admin-uptime"],
    queryFn: () =>
      apiClient<{ services: UptimeSummary[] }>({
        url: "/api/v1/admin/operations/uptime",
        method: "GET",
      }),
    refetchInterval: 60_000,
  });

  const services = data?.services ?? [];
  if (services.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {services.map((s) => {
        const pct = s.uptime_24h;
        const color =
          pct >= 99.9
            ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
            : pct >= 99
              ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
        return (
          <div
            key={s.service_name}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium",
              color,
            )}
          >
            {s.service_name}: {pct.toFixed(1)}%
          </div>
        );
      })}
    </div>
  );
}
