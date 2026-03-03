import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Upload } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useDebounce } from "@/hooks/use-debounce";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { DocumentTable } from "@/components/documents/document-table";
import { DocumentFilters } from "@/components/documents/document-filters";
import type { DocumentResponse, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/documents/")({
  component: DocumentsPage,
});

function DocumentsPage() {
  const navigate = useNavigate();
  const matterId = useAppStore((s) => s.matterId);
  const datasetId = useAppStore((s) => s.datasetId);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);
  const [docType, setDocType] = useState("all");
  const [privilege, setPrivilege] = useState("all");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["documents", matterId, debouncedSearch, docType, privilege, offset, datasetId],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: {
          q: debouncedSearch || undefined,
          document_type: docType !== "all" ? docType : undefined,
          dataset_id: datasetId || undefined,
          offset,
          limit,
        },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-4 animate-page-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} documents` : "Loading..."}
          </p>
        </div>
        <Button onClick={() => navigate({ to: "/documents/import" })}>
          <Upload className="mr-2 h-4 w-4" />
          Import
        </Button>
      </div>

      <DocumentFilters
        search={search}
        onSearchChange={(v) => { setSearch(v); setOffset(0); }}
        docType={docType}
        onDocTypeChange={(v) => { setDocType(v); setOffset(0); }}
        privilege={privilege}
        onPrivilegeChange={(v) => { setPrivilege(v); setOffset(0); }}
      />

      <DocumentTable data={data?.items ?? []} loading={isLoading} />

      {data && <Pagination total={data.total} offset={offset} limit={limit} onOffsetChange={setOffset} />}
    </div>
  );
}
