import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

export const Route = createLazyFileRoute("/admin/pages")({
  component: PagesPage,
});

interface FeatureFlagDetail {
  flag_name: string;
  display_name: string;
  description: string;
  category: string;
  risk_level: string;
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

const PAGE_GROUPS = [
  {
    title: "Main",
    flags: [
      "enable_page_chat",
      "enable_page_documents",
      "enable_page_ingest",
      "enable_page_datasets",
      "enable_page_entities",
    ],
  },
  {
    title: "Analysis",
    flags: [
      "enable_page_comms_matrix",
      "enable_page_timeline",
      "enable_page_network_graph",
    ],
  },
  {
    title: "Review",
    flags: [
      "enable_page_hot_docs",
      "enable_page_result_set",
      "enable_page_exports",
      "enable_page_case_setup",
    ],
  },
];

function PagesPage() {
  const notify = useNotifications();
  const queryClient = useQueryClient();

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
      notify.success(
        `${result.display_name} ${result.enabled ? "shown" : "hidden"} in sidebar.`,
      );
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to update page visibility");
    },
  });

  const pageFlags = (data?.items ?? []).filter((f) => f.category === "pages");
  const flagMap = new Map(pageFlags.map((f) => [f.flag_name, f]));

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Pages</h1>
        <p className="text-sm text-muted-foreground">
          Control which pages are visible in the sidebar navigation for all users.
          Admin pages are always visible.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading...
        </div>
      ) : (
        PAGE_GROUPS.map((group) => {
          const groupFlags = group.flags
            .map((name) => flagMap.get(name))
            .filter((f): f is FeatureFlagDetail => !!f);
          if (groupFlags.length === 0) return null;

          return (
            <Card key={group.title}>
              <CardHeader>
                <CardTitle className="text-base">{group.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {groupFlags.map((flag) => (
                  <div
                    key={flag.flag_name}
                    className="flex items-center justify-between rounded-md px-3 py-3 hover:bg-muted/40 transition-colors"
                  >
                    <div className="flex-1 min-w-0 pr-4">
                      <span className="text-sm font-medium">{flag.display_name}</span>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {flag.description}
                      </p>
                    </div>
                    <Switch
                      checked={flag.enabled}
                      disabled={toggleMutation.isPending}
                      onCheckedChange={(checked) =>
                        toggleMutation.mutate({
                          flagName: flag.flag_name,
                          enabled: checked,
                        })
                      }
                    />
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}
