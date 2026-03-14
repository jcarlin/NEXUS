import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Info } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export const Route = createFileRoute("/admin/settings")({
  component: SettingsPage,
});

// --- Types ---

interface SettingDetail {
  setting_name: string;
  display_name: string;
  description: string;
  category: string;
  setting_type: "int" | "float" | "string";
  risk_level: "safe" | "cache_clear" | "restart";
  value: number | string;
  env_default: number | string;
  min_value: number | null;
  max_value: number | null;
  unit: string | null;
  step: number | null;
  is_override: boolean;
  updated_at: string | null;
  updated_by: string | null;
  requires_flag: string | null;
  flag_enabled: boolean | null;
}

interface SettingListResponse {
  items: SettingDetail[];
}

interface SettingUpdateResponse extends SettingDetail {
  caches_cleared: string[];
  restart_required: boolean;
}

// --- Constants ---

const CATEGORY_ORDER = [
  "retrieval",
  "adaptive_depth",
  "query",
  "agent",
  "ingestion",
  "visual",
  "auth",
];

const CATEGORY_LABELS: Record<string, string> = {
  retrieval: "Retrieval & Embedding",
  adaptive_depth: "Adaptive Retrieval Depth",
  query: "Query Pipeline",
  agent: "Agent",
  ingestion: "Ingestion & Processing",
  visual: "Visual Reranking",
  auth: "Auth & Limits",
};

const RISK_STYLES: Record<string, string> = {
  safe: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  cache_clear:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  restart: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const RISK_LABELS: Record<string, string> = {
  safe: "Safe",
  cache_clear: "Cache Clear",
  restart: "Restart Required",
};

// --- Page ---

function SettingsPage() {
  const notify = useNotifications();
  const queryClient = useQueryClient();
  const [pendingValues, setPendingValues] = useState<
    Record<string, string>
  >({});
  const [confirmSetting, setConfirmSetting] = useState<{
    setting: SettingDetail;
    newValue: number | string;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: () =>
      apiClient<SettingListResponse>({
        url: "/api/v1/admin/settings",
        method: "GET",
      }),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      settingName,
      value,
    }: {
      settingName: string;
      value: number | string;
    }) =>
      apiClient<SettingUpdateResponse>({
        url: `/api/v1/admin/settings/${settingName}`,
        method: "PUT",
        data: { value },
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
      // Clear local pending value
      setPendingValues((prev) => {
        const next = { ...prev };
        delete next[result.setting_name];
        return next;
      });
      if (result.restart_required) {
        notify.info(
          `${result.display_name} saved. Takes effect after server restart.`
        );
      } else if (result.caches_cleared.length > 0) {
        notify.success(
          `${result.display_name} updated to ${result.value}. Cleared ${result.caches_cleared.length} cache(s).`
        );
      } else {
        notify.success(
          `${result.display_name} updated to ${result.value}.`
        );
      }
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to update setting"
      );
    },
  });

  const resetMutation = useMutation({
    mutationFn: (settingName: string) =>
      apiClient<void>({
        url: `/api/v1/admin/settings/${settingName}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      notify.success("Reset to environment default.");
      queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to reset setting"
      );
    },
  });

  function parseValue(
    raw: string,
    settingType: "int" | "float" | "string"
  ): number | string {
    if (settingType === "int") return parseInt(raw, 10);
    if (settingType === "float") return parseFloat(raw);
    return raw;
  }

  function handleSave(setting: SettingDetail) {
    const raw = pendingValues[setting.setting_name];
    if (raw === undefined) return;

    const parsed = parseValue(raw, setting.setting_type);
    if (typeof parsed === "number" && isNaN(parsed)) {
      notify.error("Invalid number.");
      return;
    }

    if (
      setting.risk_level === "cache_clear" ||
      setting.risk_level === "restart"
    ) {
      setConfirmSetting({ setting, newValue: parsed });
    } else {
      updateMutation.mutate({
        settingName: setting.setting_name,
        enabled: parsed,
        value: parsed,
      } as { settingName: string; value: number | string });
    }
  }

  function confirmSave() {
    if (!confirmSetting) return;
    updateMutation.mutate({
      settingName: confirmSetting.setting.setting_name,
      value: confirmSetting.newValue,
    });
    setConfirmSetting(null);
  }

  const settings = data?.items ?? [];

  // Group by category
  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    label: CATEGORY_LABELS[cat] ?? cat,
    settings: settings.filter((s) => s.category === cat),
  })).filter((g) => g.settings.length > 0);

  return (
    <div className="space-y-6 animate-page-in max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Tune numeric parameters at runtime. Changes to &quot;Safe&quot; and
          &quot;Cache Clear&quot; settings take effect immediately.
          &quot;Restart Required&quot; settings are saved but need a server
          restart.
        </p>
      </div>

      {/* Setting cards by category */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading settings...
        </div>
      ) : (
        grouped.map((group) => (
          <Card key={group.category}>
            <CardHeader className="border-b">
              <CardTitle className="text-base">{group.label}</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              {group.settings.map((setting) => {
                const isDisabledByFlag =
                  setting.requires_flag !== null &&
                  setting.flag_enabled === false;
                const pendingRaw =
                  pendingValues[setting.setting_name];
                const hasChanged =
                  pendingRaw !== undefined &&
                  pendingRaw !== String(setting.value);

                return (
                  <div
                    key={setting.setting_name}
                    className={`flex items-center justify-between px-3 py-3 transition-colors ${
                      isDisabledByFlag
                        ? "opacity-50"
                        : "hover:bg-muted/40"
                    }`}
                  >
                    {/* Left: name + description */}
                    <div className="flex-1 min-w-0 pr-4">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">
                          {setting.display_name}
                        </span>
                        <Badge
                          variant="secondary"
                          className={`text-[10px] px-1.5 py-0 ${RISK_STYLES[setting.risk_level] ?? ""}`}
                        >
                          {RISK_LABELS[setting.risk_level] ??
                            setting.risk_level}
                        </Badge>
                        {setting.is_override && (
                          <Badge
                            variant="outline"
                            className="text-[10px] px-1.5 py-0 border-blue-300 text-blue-700 dark:border-blue-700 dark:text-blue-300"
                          >
                            DB Override
                          </Badge>
                        )}
                        {isDisabledByFlag && (
                          <Tooltip>
                            <TooltipTrigger>
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 py-0 border-gray-300 text-gray-500"
                              >
                                <Info className="h-3 w-3 mr-0.5" />
                                Flag Off
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent>
                              Enable{" "}
                              <code className="text-xs">
                                {setting.requires_flag}
                              </code>{" "}
                              on the Feature Flags page first
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                        {setting.description}
                      </p>
                    </div>

                    {/* Right: input + actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      {setting.is_override && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs text-muted-foreground"
                          disabled={
                            resetMutation.isPending || isDisabledByFlag
                          }
                          onClick={() =>
                            resetMutation.mutate(setting.setting_name)
                          }
                        >
                          <RotateCcw className="mr-1 h-3 w-3" />
                          Reset
                        </Button>
                      )}
                      <div className="flex items-center gap-1.5">
                        <Input
                          type={
                            setting.setting_type === "string"
                              ? "text"
                              : "number"
                          }
                          className="h-8 w-24 text-sm tabular-nums"
                          value={
                            pendingRaw ?? String(setting.value)
                          }
                          min={setting.min_value ?? undefined}
                          max={setting.max_value ?? undefined}
                          step={
                            setting.step ??
                            (setting.setting_type === "float"
                              ? 0.01
                              : 1)
                          }
                          disabled={isDisabledByFlag}
                          onChange={(e) =>
                            setPendingValues((prev) => ({
                              ...prev,
                              [setting.setting_name]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSave(setting);
                          }}
                        />
                        {setting.unit && (
                          <span className="text-xs text-muted-foreground whitespace-nowrap">
                            {setting.unit}
                          </span>
                        )}
                      </div>
                      {hasChanged && (
                        <Button
                          size="sm"
                          className="h-7 text-xs"
                          disabled={
                            updateMutation.isPending || isDisabledByFlag
                          }
                          onClick={() => handleSave(setting)}
                        >
                          Save
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        ))
      )}

      {/* Confirmation dialog for cache_clear / restart settings */}
      <AlertDialog
        open={!!confirmSetting}
        onOpenChange={() => setConfirmSetting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmSetting?.setting.risk_level === "restart"
                ? "Restart Required"
                : "Confirm Cache Clear"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmSetting?.setting.risk_level === "restart" ? (
                <>
                  Changing{" "}
                  <strong>
                    {confirmSetting?.setting.display_name}
                  </strong>{" "}
                  requires a server restart to take effect. The value
                  will be saved to the database immediately.
                </>
              ) : (
                <>
                  Changing{" "}
                  <strong>
                    {confirmSetting?.setting.display_name}
                  </strong>{" "}
                  will clear cached model/service instances and rebuild
                  them on the next request. This may cause a brief
                  delay.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmSave}>
              Save
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
