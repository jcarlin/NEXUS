import { useCallback } from "react";
import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Loader2, AlertCircle } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiClient } from "@/api/client";
import { QueryPipeline } from "@/components/admin/architecture/query-pipeline";
import { IngestionPipeline } from "@/components/admin/architecture/ingestion-pipeline";
import { ModelConfigTable } from "@/components/admin/architecture/model-config-table";

export const Route = createLazyFileRoute("/admin/architecture")({
  component: ArchitecturePage,
});

interface FeatureFlag {
  flag_name: string;
  enabled: boolean;
  display_name: string;
  description: string;
  category: string;
  risk_level: string;
}

interface LLMTier {
  tier: string;
  provider_label: string | null;
  provider_type: string | null;
  model: string | null;
}

interface EmbeddingConfig {
  provider: string;
  model: string;
  dimensions: number;
}

interface LLMConfigOverview {
  providers: unknown[];
  tiers: LLMTier[];
  env_defaults: Record<string, string>;
  embedding: EmbeddingConfig;
}

interface SettingDetail {
  setting_name: string;
  value: number | string;
  category: string;
  unit: string | null;
}

function ArchitecturePage() {
  const queryClient = useQueryClient();

  const { data: flags, isLoading: flagsLoading, isError: flagsError } = useQuery({
    queryKey: ["admin-feature-flags"],
    queryFn: () =>
      apiClient<{ items: FeatureFlag[] }>({
        url: "/api/v1/admin/feature-flags",
        method: "GET",
      }),
    staleTime: 30_000,
  });

  const { data: llmConfig, isLoading: llmLoading } = useQuery({
    queryKey: ["admin-llm-config"],
    queryFn: () =>
      apiClient<LLMConfigOverview>({
        url: "/api/v1/admin/llm-config",
        method: "GET",
      }),
    staleTime: 30_000,
  });

  const { data: settingsData, isLoading: settingsLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: () =>
      apiClient<{ items: SettingDetail[] }>({
        url: "/api/v1/admin/settings",
        method: "GET",
      }),
    staleTime: 30_000,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ flagName, enabled }: { flagName: string; enabled: boolean }) =>
      apiClient<unknown>({
        url: `/api/v1/admin/feature-flags/${flagName}`,
        method: "PUT",
        data: { enabled },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-feature-flags"] });
    },
  });

  const handleToggle = useCallback(
    (flagName: string, newValue: boolean) => {
      toggleMutation.mutate({ flagName, enabled: newValue });
    },
    [toggleMutation],
  );

  const isLoading = flagsLoading || llmLoading || settingsLoading;

  // Build lookup maps
  const flagMap = new Map<string, boolean>();
  if (flags?.items) {
    for (const f of flags.items) {
      flagMap.set(f.flag_name, f.enabled);
    }
  }

  const settingsMap = new Map<string, string | number>();
  if (settingsData?.items) {
    for (const s of settingsData.items) {
      settingsMap.set(s.setting_name, s.value);
    }
  }

  const queryModel = llmConfig?.tiers?.find((t) => t.tier === "query")?.model ?? null;
  const embeddingInfo = llmConfig?.embedding ?? null;

  if (isLoading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (flagsError && flagMap.size === 0) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-muted-foreground">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm">Backend unavailable — start the server to view live configuration</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline Architecture</h1>
        <p className="text-sm text-muted-foreground">
          Live system configuration — reflects current feature flags, models, and settings
        </p>
      </div>

      <Tabs defaultValue="query">
        <TabsList>
          <TabsTrigger value="query">Query Pipeline</TabsTrigger>
          <TabsTrigger value="ingestion">Ingestion Pipeline</TabsTrigger>
        </TabsList>
        <TabsContent value="query" className="mt-6">
          <QueryPipeline
            flagMap={flagMap}
            queryModel={queryModel}
            embeddingInfo={embeddingInfo}
            settings={settingsMap}
            onToggleFlag={handleToggle}
          />
        </TabsContent>
        <TabsContent value="ingestion" className="mt-6">
          <IngestionPipeline
            flagMap={flagMap}
            embeddingInfo={embeddingInfo}
            settings={settingsMap}
            onToggleFlag={handleToggle}
          />
        </TabsContent>
      </Tabs>

      <div className="pt-4">
        <h2 className="mb-3 text-lg font-semibold">Current Model Configuration</h2>
        <ModelConfigTable
          tiers={llmConfig?.tiers ?? []}
          embedding={embeddingInfo}
        />
      </div>
    </div>
  );
}
