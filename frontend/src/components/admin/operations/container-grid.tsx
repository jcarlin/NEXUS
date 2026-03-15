import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { ContainerCard, type ContainerInfo } from "./container-card";

export function ContainerGrid() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin-containers"],
    queryFn: () =>
      apiClient<{ containers: ContainerInfo[] }>({
        url: "/api/v1/admin/operations/containers",
        method: "GET",
      }),
    refetchInterval: (query) => (query.state.status === "error" ? false : 10_000),
    retry: 1,
  });

  if (isLoading)
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading containers...
      </div>
    );

  if (isError)
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Docker unavailable</AlertTitle>
        <AlertDescription>
          {error instanceof Error
            ? error.message
            : "Could not connect to the Docker daemon. Ensure Docker is running."}
        </AlertDescription>
      </Alert>
    );

  const containers = data?.containers ?? [];
  if (containers.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        No containers found. Is Docker running?
      </p>
    );

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {containers.map((c) => (
        <ContainerCard key={c.container_id} container={c} />
      ))}
    </div>
  );
}
