import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { apiClient } from "@/api/client";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface ChainNode {
  name: string;
  title?: string | null;
}

interface ReportingChainResponse {
  person: string;
  chains: ChainNode[][];
}

interface ReportingChainProps {
  personName: string;
}

export function ReportingChain({ personName }: ReportingChainProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["reporting-chain", personName],
    queryFn: () =>
      apiClient<ReportingChainResponse>({
        url: `/api/v1/graph/reporting-chain/${encodeURIComponent(personName)}`,
        method: "GET",
      }),
    enabled: !!personName,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4" />
            Reporting Chain
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4" />
            Reporting Chain
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">
            Failed to load reporting chain.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!data || data.chains.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4" />
            Reporting Chain
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No reporting chain found for {personName}.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4" />
          Reporting Chain
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.chains.map((chain, ci) => (
          <div key={ci} className="space-y-1">
            {data.chains.length > 1 && (
              <p className="text-xs font-medium text-muted-foreground mb-2">
                Chain {ci + 1}
              </p>
            )}
            <ol className="space-y-1">
              {chain.map((node, ni) => (
                <li
                  key={ni}
                  className="flex items-center gap-2 text-sm"
                  style={{ paddingLeft: `${ni * 16}px` }}
                >
                  <span
                    className={
                      node.name.toLowerCase() === personName.toLowerCase()
                        ? "font-semibold"
                        : ""
                    }
                  >
                    {ni > 0 && (
                      <span className="text-muted-foreground mr-1">
                        &rarr;
                      </span>
                    )}
                    {node.name}
                  </span>
                  {node.title && (
                    <span className="text-xs text-muted-foreground">
                      ({node.title})
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
