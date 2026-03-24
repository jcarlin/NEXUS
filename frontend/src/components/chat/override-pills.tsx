import { useMemo } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useOverrideStore, EMPTY_OVERRIDES } from "@/stores/override-store";
import { useFeatureFlag } from "@/hooks/use-feature-flags";
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

interface OverridePillsProps {
  threadId: string;
}

export function OverridePills({ threadId }: OverridePillsProps) {
  const enabled = useFeatureFlag("retrieval_overrides");
  const overrides = useOverrideStore((s) => s.threadOverrides[threadId] ?? EMPTY_OVERRIDES);
  const setOverride = useOverrideStore((s) => s.setOverride);

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

  const entries = Object.entries(overrides);
  if (!enabled || entries.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {entries.map(([flag, value]) => {
        const detail = flagMap.get(flag);
        const label = detail?.display_name ?? flag;

        return (
          <Badge
            key={flag}
            variant={value ? "default" : "secondary"}
            className={cn(
              "gap-1 py-0 pr-1 text-[10px] font-normal",
              !value && "text-muted-foreground",
            )}
          >
            {value ? label : `No ${label}`}
            <button
              type="button"
              className="ml-0.5 rounded-full p-0.5 hover:bg-background/20"
              onClick={() => setOverride(threadId, flag, null)}
              aria-label={`Remove ${label} override`}
            >
              <X className="size-2.5" />
            </button>
          </Badge>
        );
      })}
    </div>
  );
}
