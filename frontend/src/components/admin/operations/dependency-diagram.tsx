import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

interface ServiceNode {
  service: string;
  status: string;
  depends_on: string[];
}

interface DependencyResponse {
  nodes: ServiceNode[];
}

const STATUS_DOT: Record<string, string> = {
  running: "bg-green-500",
  healthy: "bg-green-500",
  stopped: "bg-red-500",
  exited: "bg-red-500",
  unhealthy: "bg-red-500",
  starting: "bg-amber-500",
  restarting: "bg-amber-500",
  unknown: "bg-gray-400",
};

export function DependencyDiagram() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-dependencies"],
    queryFn: () =>
      apiClient<DependencyResponse>({
        url: "/api/v1/admin/operations/dependencies",
        method: "GET",
      }),
    staleTime: Infinity,
  });

  if (isLoading)
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading dependency map...
      </div>
    );

  const services = data?.nodes ?? [];
  if (services.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        No dependency information available.
      </p>
    );

  // Group into tiers: services with no dependencies first, then services that depend on them
  const serviceMap = new Map(services.map((s) => [s.service, s]));
  const tiers: ServiceNode[][] = [];
  const placed = new Set<string>();

  // Tier 0: no dependencies
  const tier0 = services.filter((s) => s.depends_on.length === 0);
  if (tier0.length > 0) {
    tiers.push(tier0);
    tier0.forEach((s) => placed.add(s.service));
  }

  // Subsequent tiers: services whose dependencies are all placed
  let maxIterations = services.length;
  while (placed.size < services.length && maxIterations-- > 0) {
    const nextTier = services.filter(
      (s) =>
        !placed.has(s.service) &&
        s.depends_on.every((d) => placed.has(d) || !serviceMap.has(d)),
    );
    if (nextTier.length === 0) {
      // Remaining services have circular or unresolvable deps -- place them
      const remaining = services.filter((s) => !placed.has(s.service));
      if (remaining.length > 0) tiers.push(remaining);
      break;
    }
    tiers.push(nextTier);
    nextTier.forEach((s) => placed.add(s.service));
  }

  return (
    <div className="space-y-6">
      {tiers.map((tier, tierIndex) => (
        <div key={tierIndex}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {tierIndex === 0
              ? "Infrastructure"
              : tierIndex === 1
                ? "Core Services"
                : `Tier ${tierIndex}`}
          </p>
          <div className="flex flex-wrap gap-3">
            {tier.map((service) => (
              <Card key={service.service} className="w-48">
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={cn(
                        "h-2.5 w-2.5 rounded-full shrink-0",
                        STATUS_DOT[service.status] ?? STATUS_DOT.unknown,
                      )}
                    />
                    <span className="text-sm font-medium truncate">
                      {service.service}
                    </span>
                  </div>
                  {service.depends_on.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {service.depends_on.map((dep) => (
                        <span
                          key={dep}
                          className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground"
                        >
                          {dep}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
          {tierIndex < tiers.length - 1 && (
            <div className="flex justify-center py-2">
              <div className="h-4 w-px bg-border" />
            </div>
          )}
        </div>
      ))}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-2 border-t">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          Running
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-amber-500" />
          Starting
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          Stopped
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-gray-400" />
          Unknown
        </div>
      </div>
    </div>
  );
}
