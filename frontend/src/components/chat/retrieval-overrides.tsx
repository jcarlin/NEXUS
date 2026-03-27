import { useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SlidersHorizontal, RotateCcw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useFeatureFlag } from "@/hooks/use-feature-flags";
import { useOverrideStore, EMPTY_OVERRIDES } from "@/stores/override-store";
import { cn } from "@/lib/utils";

interface OverrideFlagDetail {
  flag_name: string;
  display_name: string;
  description: string;
  category: "logic" | "di_gated";
  global_enabled: boolean;
  can_enable: boolean;
  can_disable: boolean;
}

interface OverrideParamDetail {
  param_name: string;
  display_name: string;
  description: string;
  param_type: "int" | "float";
  default_value: number;
  min_value: number;
  max_value: number;
  step: number | null;
}

interface AvailableOverridesResponse {
  flags: OverrideFlagDetail[];
  params: OverrideParamDetail[];
}

interface RetrievalOverridesProps {
  threadId: string;
}

const FLAG_GROUPS: { label: string; flags: string[] }[] = [
  {
    label: "Search",
    flags: ["enable_hyde", "enable_multi_query_expansion", "enable_retrieval_grading", "enable_adaptive_retrieval_depth"],
  },
  {
    label: "Analysis",
    flags: ["enable_citation_verification", "enable_self_reflection", "enable_question_decomposition", "enable_prompt_routing"],
  },
  {
    label: "Data Sources",
    flags: ["enable_text_to_cypher", "enable_text_to_sql"],
  },
  {
    label: "Models",
    flags: ["enable_reranker", "enable_sparse_embeddings", "enable_visual_embeddings"],
  },
];

/** Maps numeric params to their parent boolean flag (disabled when parent is off). */
const PARAM_DEPENDENCIES: Record<string, string> = {
  hyde_blend_ratio: "enable_hyde",
  multi_query_count: "enable_multi_query_expansion",
  reranker_top_n: "enable_reranker",
  self_reflection_faithfulness_threshold: "enable_self_reflection",
};

export function RetrievalOverrides({ threadId }: RetrievalOverridesProps) {
  const enabled = useFeatureFlag("retrieval_overrides");
  const overrides = useOverrideStore((s) => s.threadOverrides[threadId] ?? EMPTY_OVERRIDES);
  const setOverride = useOverrideStore((s) => s.setOverride);
  const clearOverrides = useOverrideStore((s) => s.clearOverrides);

  const { data } = useQuery({
    queryKey: ["retrieval-options"],
    queryFn: () =>
      apiClient<AvailableOverridesResponse>({
        url: "/api/v1/query/retrieval-options",
        method: "GET",
      }),
    staleTime: 5 * 60 * 1000,
    enabled,
  });

  const flagMap = useMemo(() => {
    if (!data?.flags) return new Map<string, OverrideFlagDetail>();
    return new Map(data.flags.map((f) => [f.flag_name, f]));
  }, [data]);

  const paramMap = useMemo(() => {
    if (!data?.params) return new Map<string, OverrideParamDetail>();
    return new Map(data.params.map((p) => [p.param_name, p]));
  }, [data]);

  const overrideCount = Object.keys(overrides).length;

  if (!enabled) return null;

  const handleToggle = (flagName: string, detail: OverrideFlagDetail) => {
    const current = overrides[flagName];
    if (current === undefined) {
      setOverride(threadId, flagName, !detail.global_enabled);
    } else if (current !== detail.global_enabled) {
      setOverride(threadId, flagName, null);
    } else {
      setOverride(threadId, flagName, !current);
    }
  };

  const isParamDisabled = (paramName: string): boolean => {
    const dep = PARAM_DEPENDENCIES[paramName];
    if (!dep) return false;
    const flagDetail = flagMap.get(dep);
    if (!flagDetail) return false;
    // Check if the flag is effectively off (override or global)
    const overrideVal = overrides[dep];
    const effectiveVal = overrideVal !== undefined ? overrideVal : flagDetail.global_enabled;
    return !effectiveVal;
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-xs"
          className="relative text-muted-foreground hover:text-foreground"
          aria-label="Retrieval overrides"
        >
          <SlidersHorizontal className="size-3.5" />
          {overrideCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
              {overrideCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <div className="border-b px-3 py-2">
          <h3 className="text-sm font-medium">Retrieval Overrides</h3>
          <p className="text-[11px] text-muted-foreground">
            Override pipeline flags and parameters for this chat
          </p>
        </div>
        <ScrollArea className="max-h-96">
          <div className="space-y-3 p-3">
            {/* Boolean flag groups */}
            {FLAG_GROUPS.map((group) => {
              const groupFlags = group.flags
                .map((name) => flagMap.get(name))
                .filter((f): f is OverrideFlagDetail => !!f);
              if (groupFlags.length === 0) return null;

              return (
                <div key={group.label}>
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                    {group.label}
                  </p>
                  <div className="space-y-1">
                    {groupFlags.map((flag) => {
                      const override = overrides[flag.flag_name];
                      const isOverridden = override !== undefined;
                      const effectiveValue = isOverridden ? override : flag.global_enabled;
                      const isDiGatedOff = flag.category === "di_gated" && !flag.global_enabled;

                      return (
                        <div
                          key={flag.flag_name}
                          className={cn(
                            "flex items-center justify-between rounded-md px-2 py-1.5 transition-colors",
                            isOverridden && "bg-accent/50",
                          )}
                        >
                          <div className="mr-3 min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span
                                className={cn(
                                  "text-xs font-medium",
                                  isDiGatedOff && "text-muted-foreground",
                                )}
                              >
                                {flag.display_name}
                              </span>
                              {isOverridden && (
                                <span className="size-1.5 rounded-full bg-primary" />
                              )}
                            </div>
                            {isDiGatedOff && (
                              <p className="text-[10px] text-muted-foreground/60">
                                Requires global enable
                              </p>
                            )}
                          </div>
                          <Switch
                            size="sm"
                            checked={!!effectiveValue}
                            onCheckedChange={() => handleToggle(flag.flag_name, flag)}
                            disabled={isDiGatedOff}
                            className={cn(!isOverridden && "opacity-50")}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {/* Numeric parameters */}
            {paramMap.size > 0 && (
              <div>
                <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                  Parameters
                </p>
                <div className="space-y-2.5">
                  {Array.from(paramMap.values()).map((param) => {
                    const override = overrides[param.param_name];
                    const isOverridden = override !== undefined;
                    const effectiveValue = typeof override === "number" ? override : param.default_value;
                    const disabled = isParamDisabled(param.param_name);
                    const step = param.step ?? (param.param_type === "int" ? 1 : 0.1);

                    return (
                      <div
                        key={param.param_name}
                        className={cn(
                          "rounded-md px-2 py-1.5 transition-colors",
                          isOverridden && "bg-accent/50",
                          disabled && "opacity-40",
                        )}
                      >
                        <div className="mb-1 flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-medium">{param.display_name}</span>
                            {isOverridden && (
                              <span className="size-1.5 rounded-full bg-primary" />
                            )}
                          </div>
                          <button
                            type="button"
                            className={cn(
                              "rounded px-1.5 py-0.5 text-[11px] font-mono tabular-nums",
                              isOverridden
                                ? "bg-primary/10 text-primary cursor-pointer hover:bg-primary/20"
                                : "text-muted-foreground",
                            )}
                            onClick={() => isOverridden && setOverride(threadId, param.param_name, null)}
                            title={isOverridden ? "Click to reset" : "Default value"}
                          >
                            {param.param_type === "float" ? effectiveValue.toFixed(2) : effectiveValue}
                          </button>
                        </div>
                        <Slider
                          value={[effectiveValue]}
                          min={param.min_value}
                          max={param.max_value}
                          step={step}
                          disabled={disabled}
                          onValueChange={([val]: number[]) => {
                            if (val === param.default_value) {
                              setOverride(threadId, param.param_name, null);
                            } else {
                              setOverride(threadId, param.param_name, val!);
                            }
                          }}
                          className={cn("h-1.5", !isOverridden && "opacity-50")}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </ScrollArea>
        {overrideCount > 0 && (
          <div className="border-t px-3 py-2">
            <Button
              variant="ghost"
              size="xs"
              className="w-full text-muted-foreground"
              onClick={() => clearOverrides(threadId)}
            >
              <RotateCcw className="size-3" />
              Reset to defaults
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
