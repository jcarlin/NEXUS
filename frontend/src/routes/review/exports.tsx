import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProductionSetList } from "@/components/exports/production-set-list";
import { ExportJobList } from "@/components/exports/export-job-list";
import { CreateProductionSetDialog } from "@/components/exports/create-production-set-dialog";
import { CreateExportDialog } from "@/components/exports/create-export-dialog";
import type { PaginatedResponse } from "@/types";
import type { ProductionSetResponse, ExportJobResponse } from "@/api/generated/schemas";

export type { ProductionSetResponse as ProductionSet, ExportJobResponse as ExportJob } from "@/api/generated/schemas";

export const Route = createFileRoute("/review/exports")({
  component: ExportsPage,
});

function ExportsPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [psOffset, setPsOffset] = useState(0);
  const [jobOffset, setJobOffset] = useState(0);
  const limit = 50;

  const productionSets = useQuery({
    queryKey: ["production-sets", matterId, psOffset],
    queryFn: () =>
      apiClient<PaginatedResponse<ProductionSetResponse>>({
        url: "/api/v1/exports/production-sets",
        method: "GET",
        params: { offset: psOffset, limit },
      }),
    enabled: !!matterId,
  });

  const exportJobs = useQuery({
    queryKey: ["export-jobs", matterId, jobOffset],
    queryFn: () =>
      apiClient<PaginatedResponse<ExportJobResponse>>({
        url: "/api/v1/exports/jobs",
        method: "GET",
        params: { offset: jobOffset, limit },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-4 animate-page-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Exports</h1>
          <p className="text-sm text-muted-foreground">
            Manage production sets and export jobs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CreateProductionSetDialog onCreated={() => productionSets.refetch()} />
          <CreateExportDialog
            productionSets={productionSets.data?.items ?? []}
            onCreated={() => exportJobs.refetch()}
          />
        </div>
      </div>

      <Tabs defaultValue="production-sets">
        <TabsList>
          <TabsTrigger value="production-sets">
            Production Sets ({productionSets.data?.total ?? 0})
          </TabsTrigger>
          <TabsTrigger value="export-jobs">
            Export Jobs ({exportJobs.data?.total ?? 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="production-sets">
          <ProductionSetList
            data={productionSets.data?.items ?? []}
            loading={productionSets.isLoading}
            total={productionSets.data?.total ?? 0}
            offset={psOffset}
            limit={limit}
            onOffsetChange={setPsOffset}
            onRefresh={() => productionSets.refetch()}
          />
        </TabsContent>

        <TabsContent value="export-jobs">
          <ExportJobList
            data={exportJobs.data?.items ?? []}
            loading={exportJobs.isLoading}
            total={exportJobs.data?.total ?? 0}
            offset={jobOffset}
            limit={limit}
            onOffsetChange={setJobOffset}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
