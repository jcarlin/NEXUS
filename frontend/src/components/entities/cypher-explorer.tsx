import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, ChevronDown, ChevronRight, ShieldAlert } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";

interface ExploreResponse {
  results: Record<string, unknown>[];
}

const ALLOWED_ROLES = new Set(["admin", "attorney"]);

export function CypherExplorer() {
  const user = useAuthStore((s) => s.user);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(true);

  const isAllowed = user && ALLOWED_ROLES.has(user.role);

  const { data, isLoading, error } = useQuery({
    queryKey: ["cypher-explore", submittedQuery],
    queryFn: () =>
      apiClient<ExploreResponse>({
        url: "/api/v1/graph/explore",
        method: "GET",
        params: { cypher: submittedQuery! },
      }),
    enabled: !!submittedQuery,
  });

  if (!isAllowed) return null;

  const handleRun = () => {
    const q = query.trim();
    if (q) setSubmittedQuery(q);
  };

  const columns =
    data && data.results.length > 0 ? Object.keys(data.results[0] as Record<string, unknown>) : [];

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
          <ShieldAlert className="h-4 w-4" />
          Advanced Query (Cypher)
        </CardTitle>
      </CardHeader>

      {!collapsed && (
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Run read-only Cypher queries against the knowledge graph. Write
            operations are rejected.
          </p>

          <textarea
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono min-h-[80px] resize-y focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="MATCH (n)-[r]->(m) RETURN n.name, type(r), m.name LIMIT 25"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Cypher query"
          />

          <div className="flex items-center gap-2">
            <Button
              onClick={handleRun}
              disabled={!query.trim() || isLoading}
              size="sm"
            >
              <Play className="mr-2 h-4 w-4" />
              Run
            </Button>
            {isLoading && (
              <span className="text-sm text-muted-foreground">Running...</span>
            )}
          </div>

          {error && (
            <p className="text-sm text-destructive">
              {error instanceof Error
                ? error.message
                : "Query execution failed."}
            </p>
          )}

          {data && data.results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Query returned no results.
            </p>
          )}

          {data && data.results.length > 0 && (
            <div className="max-h-[400px] overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {columns.map((col) => (
                      <TableHead key={col} className="text-xs">
                        {col}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.results.map((row, ri) => (
                    <TableRow key={ri}>
                      {columns.map((col) => (
                        <TableCell key={col} className="text-xs font-mono">
                          {typeof row[col] === "object"
                            ? JSON.stringify(row[col])
                            : String(row[col] ?? "")}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
