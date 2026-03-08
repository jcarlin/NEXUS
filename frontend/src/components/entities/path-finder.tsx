import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronDown, ChevronRight, ArrowRight } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface PathResult {
  nodes: string[];
  relationships: string[];
  hops: number;
}

interface PathResponse {
  entity_a: string;
  entity_b: string;
  paths: PathResult[];
}

export function PathFinder() {
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [searchParams, setSearchParams] = useState<{
    source: string;
    target: string;
  } | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["graph-path", searchParams?.source, searchParams?.target],
    queryFn: () =>
      apiClient<PathResponse>({
        url: "/api/v1/graph/path",
        method: "GET",
        params: {
          entity_a: searchParams!.source,
          entity_b: searchParams!.target,
        },
      }),
    enabled: !!searchParams,
  });

  const handleSearch = () => {
    const s = source.trim();
    const t = target.trim();
    if (s && t) {
      setSearchParams({ source: s, target: t });
    }
  };

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setCollapsed(!collapsed)}
      >
        <CardTitle className="flex items-center gap-2 text-base">
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
          Path Finder
        </CardTitle>
      </CardHeader>

      {!collapsed && (
        <CardContent className="space-y-4">
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <label
                htmlFor="path-source"
                className="text-xs text-muted-foreground"
              >
                Source entity
              </label>
              <Input
                id="path-source"
                placeholder="e.g. John Smith"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>
            <div className="flex-1 space-y-1">
              <label
                htmlFor="path-target"
                className="text-xs text-muted-foreground"
              >
                Target entity
              </label>
              <Input
                id="path-target"
                placeholder="e.g. Acme Corp"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>
            <Button
              onClick={handleSearch}
              disabled={!source.trim() || !target.trim() || isLoading}
              size="sm"
            >
              <Search className="mr-2 h-4 w-4" />
              Find Path
            </Button>
          </div>

          {isLoading && (
            <p className="text-sm text-muted-foreground">Searching...</p>
          )}

          {error && (
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : "Failed to find path."}
            </p>
          )}

          {data && data.paths.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No path found between {data.entity_a} and {data.entity_b}.
            </p>
          )}

          {data && data.paths.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Found {data.paths.length} path(s)
              </p>
              {data.paths.map((path, pi) => (
                <div
                  key={pi}
                  className="rounded-md border p-3 space-y-2"
                >
                  <p className="text-xs font-medium text-muted-foreground">
                    Path {pi + 1}
                  </p>
                  <div className="flex items-center gap-1 flex-wrap">
                    {path.nodes.map((nodeName, ni) => (
                      <span key={ni} className="flex items-center gap-1">
                        {ni > 0 && (
                          <span className="flex items-center gap-0.5 text-muted-foreground">
                            <ArrowRight className="h-3 w-3" />
                            {path.relationships[ni - 1] != null && (
                              <Badge
                                variant="outline"
                                className="text-[10px] font-normal"
                              >
                                {path.relationships[ni - 1]}
                              </Badge>
                            )}
                            <ArrowRight className="h-3 w-3" />
                          </span>
                        )}
                        <Badge variant="secondary" className="text-xs">
                          {nodeName}
                        </Badge>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
