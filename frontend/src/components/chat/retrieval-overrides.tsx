import { useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
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

interface AvailableOverridesResponse {
  flags: OverrideFlagDetail[];
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

  const overrideCount = Object.keys(overrides).length;

  if (!enabled) return null;

  const handleToggle = (flagName: string, detail: OverrideFlagDetail) => {
    const current = overrides[flagName];
    if (current === undefined) {
      // No override yet -> set to opposite of global
      setOverride(threadId, flagName, !detail.global_enabled);
    } else if (current !== detail.global_enabled) {
      // Overridden to opposite -> flip to same as global (which means remove)
      setOverride(threadId, flagName, null);
    } else {
      // Overridden to same as global -> flip to opposite
      setOverride(threadId, flagName, !current);
    }
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
            Override pipeline flags for this chat
          </p>
        </div>
        <ScrollArea className="max-h-80">
          <div className="space-y-3 p-3">
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
                            checked={effectiveValue}
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
