import { useState } from "react";
import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Server } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export const Route = createLazyFileRoute("/admin/feature-flags")({
  component: FeatureFlagsPage,
});

// --- Types ---

interface FeatureFlagDetail {
  flag_name: string;
  display_name: string;
  description: string;
  category: string;
  risk_level: "safe" | "cache_clear" | "restart";
  enabled: boolean;
  is_override: boolean;
  env_default: boolean;
  depends_on: string[];
  updated_at: string | null;
  updated_by: string | null;
}

interface FeatureFlagListResponse {
  items: FeatureFlagDetail[];
}

interface FeatureFlagUpdateResponse extends FeatureFlagDetail {
  caches_cleared: string[];
  restart_required: boolean;
  cascaded: string[];
}

// --- Constants ---

const CATEGORY_ORDER = [
  "retrieval",
  "query",
  "entity_graph",
  "ingestion",
  "intelligence",
  "audit",
  "integrations",
];

const CATEGORY_LABELS: Record<string, string> = {
  retrieval: "Retrieval & Embedding",
  query: "Query Pipeline",
  entity_graph: "Entity & Graph",
  ingestion: "Ingestion Pipeline",
  intelligence: "Intelligence",
  audit: "Audit & Compliance",
  integrations: "Integrations",
};

const RISK_STYLES: Record<string, string> = {
  safe: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  cache_clear: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  restart: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const RISK_LABELS: Record<string, string> = {
  safe: "Safe",
  cache_clear: "Cache Clear",
  restart: "Restart Required",
};

// --- Page ---

function FeatureFlagsPage() {
  const notify = useNotifications();
  const queryClient = useQueryClient();
  const [confirmFlag, setConfirmFlag] = useState<{
    flag: FeatureFlagDetail;
    newValue: boolean;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-feature-flags"],
    queryFn: () =>
      apiClient<FeatureFlagListResponse>({
        url: "/api/v1/admin/feature-flags",
        method: "GET",
      }),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ flagName, enabled }: { flagName: string; enabled: boolean }) =>
      apiClient<FeatureFlagUpdateResponse>({
        url: `/api/v1/admin/feature-flags/${flagName}`,
        method: "PUT",
        data: { enabled },
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["admin-feature-flags"] });
      queryClient.invalidateQueries({ queryKey: ["feature-flags"] });
      if (result.restart_required) {
        notify.info(
          `${result.display_name} saved. Takes effect after server restart. Go to Operations page to restart.`,
        );
      } else if (result.caches_cleared.length > 0) {
        notify.success(
          `${result.display_name} ${result.enabled ? "enabled" : "disabled"}. Cleared ${result.caches_cleared.length} cache(s).`,
        );
      } else {
        notify.success(`${result.display_name} ${result.enabled ? "enabled" : "disabled"}.`);
      }
      if (result.cascaded.length > 0) {
        const names = result.cascaded.map((f) => flagDisplayName(f)).join(", ");
        notify.info(`Also ${result.enabled ? "enabled" : "disabled"}: ${names}`);
      }
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to update flag");
    },
  });

  const resetMutation = useMutation({
    mutationFn: (flagName: string) =>
      apiClient<void>({
        url: `/api/v1/admin/feature-flags/${flagName}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      notify.success("Reset to environment default.");
      queryClient.invalidateQueries({ queryKey: ["admin-feature-flags"] });
      queryClient.invalidateQueries({ queryKey: ["feature-flags"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to reset flag");
    },
  });

  function flagDisplayName(flagName: string): string {
    const found = flags.find((f) => f.flag_name === flagName);
    return found?.display_name ?? flagName;
  }

  function computeCascade(flag: FeatureFlagDetail, newValue: boolean): string[] {
    if (newValue) {
      // Enabling: unmet prerequisites
      return flag.depends_on.filter((dep) => {
        const depFlag = flags.find((f) => f.flag_name === dep);
        return depFlag && !depFlag.enabled;
      });
    } else {
      // Disabling: active dependents
      return flags
        .filter((f) => f.depends_on.includes(flag.flag_name) && f.enabled)
        .map((f) => f.flag_name);
    }
  }

  function handleToggle(flag: FeatureFlagDetail, newValue: boolean) {
    const cascade = computeCascade(flag, newValue);
    if (flag.risk_level === "cache_clear" || flag.risk_level === "restart" || cascade.length > 0) {
      setConfirmFlag({ flag, newValue });
    } else {
      toggleMutation.mutate({ flagName: flag.flag_name, enabled: newValue });
    }
  }

  function confirmToggle() {
    if (!confirmFlag) return;
    toggleMutation.mutate({
      flagName: confirmFlag.flag.flag_name,
      enabled: confirmFlag.newValue,
    });
    setConfirmFlag(null);
  }

  const flags = (data?.items ?? []).map((f) => ({
    ...f,
    depends_on: f.depends_on ?? [],
  }));

  // Group by category
  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    label: CATEGORY_LABELS[cat] ?? cat,
    flags: flags.filter((f) => f.category === cat),
  })).filter((g) => g.flags.length > 0);

  // Check if any ingestion flags are present
  const hasIngestionFlags = flags.some(
    (f) => f.category === "ingestion" && f.is_override,
  );

  return (
    <div className="space-y-6 animate-page-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Feature Flags</h1>
        <p className="text-sm text-muted-foreground">
          Toggle feature flags at runtime. Changes to &quot;Safe&quot; and &quot;Cache Clear&quot; flags
          take effect immediately. &quot;Restart Required&quot; flags are saved but need a server restart.
        </p>
      </div>

      {/* Celery info */}
      {hasIngestionFlags && (
        <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 p-3 dark:border-blue-900 dark:bg-blue-950">
          <Server className="h-4 w-4 text-blue-600 dark:text-blue-500 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-800 dark:text-blue-200">
            Ingestion pipeline flag changes take effect on the next background task execution.
          </p>
        </div>
      )}

      {/* Flag cards by category */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading flags...
        </div>
      ) : (
        grouped.map((group) => (
          <Card key={group.category}>
            <CardHeader>
              <CardTitle className="text-base">{group.label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {group.flags.map((flag) => (
                <div
                  key={flag.flag_name}
                  className="flex items-center justify-between rounded-md px-3 py-3 hover:bg-muted/40 transition-colors"
                >
                  <div className="flex-1 min-w-0 pr-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{flag.display_name}</span>
                      <Badge
                        variant="secondary"
                        className={`text-[10px] px-1.5 py-0 ${RISK_STYLES[flag.risk_level] ?? ""}`}
                      >
                        {RISK_LABELS[flag.risk_level] ?? flag.risk_level}
                      </Badge>
                      {flag.is_override && (
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-blue-300 text-blue-700 dark:border-blue-700 dark:text-blue-300">
                          DB Override
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {flag.description}
                    </p>
                    {flag.depends_on.length > 0 && (
                      <p className="text-xs text-muted-foreground/70 mt-0.5">
                        Requires: {flag.depends_on.map((dep) => flagDisplayName(dep)).join(", ")}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {flag.is_override && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-muted-foreground"
                        disabled={resetMutation.isPending}
                        onClick={() => resetMutation.mutate(flag.flag_name)}
                      >
                        <RotateCcw className="mr-1 h-3 w-3" />
                        Reset
                      </Button>
                    )}
                    <Switch
                      checked={flag.enabled}
                      disabled={toggleMutation.isPending}
                      onCheckedChange={(checked) => handleToggle(flag, checked)}
                    />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))
      )}

      {/* Confirmation dialog for cache_clear / restart flags */}
      <AlertDialog open={!!confirmFlag} onOpenChange={() => setConfirmFlag(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmFlag?.flag.risk_level === "restart"
                ? "Restart Required"
                : "Confirm Cache Clear"}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {confirmFlag?.flag.risk_level === "restart" ? (
                  <p>
                    <strong>{confirmFlag?.flag.display_name}</strong> requires a server restart to
                    take effect. The change will be saved to the database immediately.
                  </p>
                ) : confirmFlag?.flag.risk_level === "cache_clear" ? (
                  <p>
                    Toggling <strong>{confirmFlag?.flag.display_name}</strong> will clear cached
                    model/service instances and rebuild them on the next request. This may cause a
                    brief delay.
                  </p>
                ) : null}
                {confirmFlag && (() => {
                  const cascade = computeCascade(confirmFlag.flag, confirmFlag.newValue);
                  if (cascade.length === 0) return null;
                  const names = cascade.map((f) => flagDisplayName(f)).join(", ");
                  return (
                    <p className="font-medium">
                      This will also {confirmFlag.newValue ? "enable" : "disable"}: {names}
                    </p>
                  );
                })()}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmToggle}>
              {confirmFlag?.newValue ? "Enable" : "Disable"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
