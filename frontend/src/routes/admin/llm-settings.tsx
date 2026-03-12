import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ChevronDown, ChevronRight, Loader2, AlertTriangle } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LLMProviderDialog } from "@/components/admin/llm-provider-dialog";
import { ModelCombobox } from "@/components/admin/model-combobox";

export const Route = createFileRoute("/admin/llm-settings")({
  component: LLMSettingsPage,
});

// --- Types ---

interface LLMProvider {
  id: string;
  provider: "anthropic" | "openai" | "gemini" | "ollama";
  label: string;
  api_key_set: boolean;
  base_url: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface LLMTierConfig {
  tier: "query" | "analysis" | "ingestion";
  provider_id: string | null;
  provider_label: string | null;
  provider_type: string | null;
  model: string | null;
  updated_at: string | null;
  updated_by: string | null;
  is_env_default: boolean;
}

interface EmbeddingConfigInfo {
  provider: string;
  model: string;
  dimensions: number;
}

interface LLMConfigOverview {
  providers: LLMProvider[];
  tiers: LLMTierConfig[];
  env_defaults: Record<string, string>;
  embedding: EmbeddingConfigInfo;
}

interface OllamaModel {
  name: string;
  size: number | null;
  modified_at: string | null;
}

interface TierCostEstimate {
  tier: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

interface CostEstimateResponse {
  period_days: number;
  tiers: TierCostEstimate[];
  total_cost_usd: number;
}

interface TestConnectionResponse {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
}

const TIER_DESCRIPTIONS: Record<string, string> = {
  query: "Agent loop, citation verification, synthesis, classification, rewriting, retrieval grading",
  analysis: "Follow-ups, sentiment, completeness, case setup, memos",
  ingestion: "Relationship extraction, contextual chunk enrichment during document processing",
};

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  openai: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  gemini: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  ollama: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
};

const COST_PERIODS = [7, 30, 90] as const;

// --- Page ---

function LLMSettingsPage() {
  const notify = useNotifications();
  const queryClient = useQueryClient();

  const [providerDialogOpen, setProviderDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<LLMProvider | null>(null);
  const [ollamaOpen, setOllamaOpen] = useState(false);
  const [costOpen, setCostOpen] = useState(false);
  const [costPeriod, setCostPeriod] = useState<number>(30);
  const [tierOverrides, setTierOverrides] = useState<
    Record<string, { provider_id: string; model: string }>
  >({});
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["llm-config"],
    queryFn: () =>
      apiClient<LLMConfigOverview>({
        url: "/api/v1/admin/llm-config",
        method: "GET",
      }),
  });

  const { data: ollamaModels, isFetching: ollamaFetching, refetch: fetchOllama } = useQuery({
    queryKey: ["llm-config", "ollama-models"],
    queryFn: () =>
      apiClient<OllamaModel[]>({
        url: "/api/v1/admin/llm-config/ollama/models",
        method: "GET",
      }),
    enabled: false,
  });

  const { data: costData, isFetching: costFetching } = useQuery({
    queryKey: ["llm-config", "cost-estimate", costPeriod],
    queryFn: () =>
      apiClient<CostEstimateResponse>({
        url: "/api/v1/admin/llm-config/cost-estimate",
        method: "GET",
        params: { period_days: costPeriod },
      }),
    enabled: costOpen,
  });

  const testMutation = useMutation({
    mutationFn: (providerId: string) => {
      setTestingProviderId(providerId);
      return apiClient<TestConnectionResponse>({
        url: `/api/v1/admin/llm-config/providers/${providerId}/test`,
        method: "POST",
      });
    },
    onSuccess: (result) => {
      if (result.success) {
        notify.success(`Connection OK (${result.latency_ms}ms)`);
      } else {
        notify.error(`Connection failed: ${result.error}`);
      }
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Test failed");
    },
    onSettled: () => {
      setTestingProviderId(null);
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (providerId: string) =>
      apiClient<void>({
        url: `/api/v1/admin/llm-config/providers/${providerId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      notify.success("Provider deactivated");
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to deactivate");
    },
  });

  const tierMutation = useMutation({
    mutationFn: ({ tier, provider_id, model }: { tier: string; provider_id: string; model: string }) =>
      apiClient<void>({
        url: `/api/v1/admin/llm-config/tiers/${tier}`,
        method: "PUT",
        data: { provider_id, model },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to update tier");
    },
  });

  const clearTierMutation = useMutation({
    mutationFn: (tier: string) =>
      apiClient<void>({
        url: `/api/v1/admin/llm-config/tiers/${tier}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      notify.success("Override cleared");
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to clear override");
    },
  });

  const applyMutation = useMutation({
    mutationFn: () =>
      apiClient<void>({
        url: "/api/v1/admin/llm-config/apply",
        method: "POST",
      }),
    onSuccess: () => {
      notify.success("Changes applied");
      setTierOverrides({});
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to apply changes");
    },
  });

  function handleApplyTiers() {
    const entries = Object.entries(tierOverrides);
    if (entries.length === 0) {
      applyMutation.mutate();
      return;
    }
    // Save each tier override, then apply
    Promise.all(
      entries.map(([tier, { provider_id, model }]) =>
        tierMutation.mutateAsync({ tier, provider_id, model }),
      ),
    ).then(() => {
      applyMutation.mutate();
    });
  }

  function getTierValue(tier: LLMTierConfig, field: "provider_id" | "model") {
    const override = tierOverrides[tier.tier];
    if (override) return override[field];
    return tier[field] ?? "";
  }

  function setTierField(tier: string, field: "provider_id" | "model", value: string) {
    setTierOverrides((prev) => ({
      ...prev,
      [tier]: {
        provider_id: prev[tier]?.provider_id ?? "",
        model: prev[tier]?.model ?? "",
        [field]: value,
      },
    }));
  }

  const providers = overview?.providers ?? [];
  const tiers = overview?.tiers ?? [];
  const activeProviders = providers.filter((p) => p.is_active);
  const hasTierChanges = Object.keys(tierOverrides).length > 0;

  return (
    <div className="space-y-6 animate-page-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">LLM Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure LLM providers, model assignments, and monitor usage costs.
        </p>
      </div>

      {/* Card 1: API Providers */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">API Providers</CardTitle>
          <Button
            size="sm"
            onClick={() => {
              setEditingProvider(null);
              setProviderDialogOpen(true);
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            Add Provider
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : providers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>API Key</TableHead>
                  <TableHead>Base URL</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.label}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={PROVIDER_COLORS[p.provider] ?? ""}>
                        {p.provider}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {p.provider === "ollama" ? (
                        <span className="text-xs text-muted-foreground">N/A</span>
                      ) : (
                        <>
                          <span className={`inline-block h-2.5 w-2.5 rounded-full ${p.api_key_set ? "bg-green-500" : "bg-red-500"}`} />
                          <span className="ml-2 text-xs text-muted-foreground">
                            {p.api_key_set ? "Set" : "Missing"}
                          </span>
                        </>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs max-w-[200px] truncate">
                      {p.base_url || "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={p.is_active ? "default" : "destructive"}>
                        {p.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setEditingProvider(p);
                            setProviderDialogOpen(true);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={testMutation.isPending}
                          onClick={() => testMutation.mutate(p.id)}
                        >
                          {testingProviderId === p.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            "Test"
                          )}
                        </Button>
                        {p.is_active && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            disabled={deactivateMutation.isPending}
                            onClick={() => deactivateMutation.mutate(p.id)}
                          >
                            Deactivate
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No providers configured.</p>
          )}
        </CardContent>
      </Card>

      {/* Card 2: Tier Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tier Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : (
            <div className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tier</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tiers.map((t) => (
                    <TableRow key={t.tier}>
                      <TableCell className="font-medium capitalize">{t.tier}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[300px]">
                        {TIER_DESCRIPTIONS[t.tier] ?? ""}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Select
                            value={getTierValue(t, "provider_id")}
                            onValueChange={(v) => setTierField(t.tier, "provider_id", v)}
                          >
                            <SelectTrigger className="w-[180px]">
                              <SelectValue placeholder="Select provider" />
                            </SelectTrigger>
                            <SelectContent>
                              {activeProviders.map((p) => (
                                <SelectItem key={p.id} value={p.id}>
                                  {p.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {t.is_env_default && !tierOverrides[t.tier] && (
                            <Badge variant="outline" className="text-xs whitespace-nowrap">
                              Using env default
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <ModelCombobox
                          providerId={getTierValue(t, "provider_id") || null}
                          value={getTierValue(t, "model")}
                          onChange={(v) => setTierField(t.tier, "model", v)}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {!t.is_env_default && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            disabled={clearTierMutation.isPending}
                            onClick={() => clearTierMutation.mutate(t.tier)}
                          >
                            Clear Override
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex justify-end">
                <Button
                  disabled={(!hasTierChanges && !applyMutation.isPending) || applyMutation.isPending}
                  onClick={handleApplyTiers}
                >
                  {applyMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Applying...
                    </>
                  ) : (
                    "Apply Changes"
                  )}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Card 3: Ollama Models (collapsible) */}
      <Card>
        <CardHeader
          className="cursor-pointer select-none flex flex-row items-center gap-2"
          onClick={() => setOllamaOpen((v) => !v)}
        >
          {ollamaOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <CardTitle className="text-base">Ollama Models</CardTitle>
        </CardHeader>
        {ollamaOpen && (
          <CardContent>
            <div className="space-y-4">
              <Button
                size="sm"
                variant="outline"
                disabled={ollamaFetching}
                onClick={() => fetchOllama()}
              >
                {ollamaFetching ? (
                  <>
                    <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    Discovering...
                  </>
                ) : (
                  "Discover Models"
                )}
              </Button>
              {ollamaModels && ollamaModels.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Model</TableHead>
                      <TableHead>Size</TableHead>
                      <TableHead>Modified</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ollamaModels.map((m) => (
                      <TableRow key={m.name}>
                        <TableCell className="font-mono text-sm">{m.name}</TableCell>
                        <TableCell className="text-sm tabular-nums">
                          {m.size != null ? `${(m.size / 1e9).toFixed(1)} GB` : "-"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {m.modified_at ? new Date(m.modified_at).toLocaleDateString() : "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : ollamaModels ? (
                <p className="text-sm text-muted-foreground">No Ollama models found.</p>
              ) : null}
            </div>
          </CardContent>
        )}
      </Card>

      {/* Card 4: Cost Estimates (collapsible) */}
      <Card>
        <CardHeader
          className="cursor-pointer select-none flex flex-row items-center gap-2"
          onClick={() => setCostOpen((v) => !v)}
        >
          {costOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <CardTitle className="text-base">Cost Estimates</CardTitle>
        </CardHeader>
        {costOpen && (
          <CardContent>
            <div className="space-y-4">
              <div className="flex gap-1">
                {COST_PERIODS.map((d) => (
                  <Button
                    key={d}
                    size="sm"
                    variant={costPeriod === d ? "default" : "outline"}
                    onClick={() => setCostPeriod(d)}
                  >
                    {d}d
                  </Button>
                ))}
              </div>
              {costFetching ? (
                <p className="text-sm text-muted-foreground">Loading cost data...</p>
              ) : costData ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Tier</TableHead>
                        <TableHead>Model</TableHead>
                        <TableHead className="text-right">Input Tokens</TableHead>
                        <TableHead className="text-right">Output Tokens</TableHead>
                        <TableHead className="text-right">Est. Cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {costData.tiers.map((c) => (
                        <TableRow key={c.tier}>
                          <TableCell className="font-medium capitalize">{c.tier}</TableCell>
                          <TableCell className="font-mono text-xs">{c.model}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {c.input_tokens.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {c.output_tokens.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            ${c.estimated_cost_usd.toFixed(4)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="flex justify-end">
                    <p className="text-sm font-medium">
                      Total: <span className="tabular-nums">${costData.total_cost_usd.toFixed(4)}</span>
                    </p>
                  </div>
                </>
              ) : null}
            </div>
          </CardContent>
        )}
      </Card>

      {/* Card 5: Embedding Configuration (read-only) */}
      {overview?.embedding && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Embedding Model</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs mb-1">Provider</p>
                <p className="font-medium">{overview.embedding.provider}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs mb-1">Model</p>
                <p className="font-mono text-xs">{overview.embedding.model}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs mb-1">Dimensions</p>
                <p className="tabular-nums">{overview.embedding.dimensions}</p>
              </div>
            </div>
            <div className="flex items-start gap-2 rounded-md border border-yellow-200 bg-yellow-50 p-3 dark:border-yellow-900 dark:bg-yellow-950">
              <AlertTriangle className="h-4 w-4 text-yellow-600 dark:text-yellow-500 mt-0.5 shrink-0" />
              <p className="text-xs text-yellow-800 dark:text-yellow-200">
                Changing the embedding model after ingestion requires re-ingesting all documents.
                Configured via environment variables.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Provider Dialog */}
      <LLMProviderDialog
        open={providerDialogOpen}
        onOpenChange={setProviderDialogOpen}
        provider={editingProvider}
      />
    </div>
  );
}
