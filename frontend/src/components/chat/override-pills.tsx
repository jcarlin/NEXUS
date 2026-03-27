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
}

interface OverrideParamDetail {
  param_name: string;
  display_name: string;
}

interface AvailableOverridesResponse {
  flags: OverrideFlagDetail[];
  params: OverrideParamDetail[];
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

  const labelMap = useMemo(() => {
    const m = new Map<string, string>();
    if (data?.flags) {
      for (const f of data.flags) m.set(f.flag_name, f.display_name);
    }
    if (data?.params) {
      for (const p of data.params) m.set(p.param_name, p.display_name);
    }
    return m;
  }, [data]);

  const entries = Object.entries(overrides);
  if (!enabled || entries.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {entries.map(([key, value]) => {
        const label = labelMap.get(key) ?? key;
        const isBoolean = typeof value === "boolean";
        const displayText = isBoolean
          ? value
            ? label
            : `No ${label}`
          : `${label}: ${typeof value === "number" && !Number.isInteger(value) ? value.toFixed(2) : value}`;

        return (
          <Badge
            key={key}
            variant={isBoolean && !value ? "secondary" : "default"}
            className={cn(
              "gap-1 py-0 pr-1 text-[10px] font-normal",
              isBoolean && !value && "text-muted-foreground",
            )}
          >
            {displayText}
            <button
              type="button"
              className="ml-0.5 rounded-full p-0.5 hover:bg-background/20"
              onClick={() => setOverride(threadId, key, null)}
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
