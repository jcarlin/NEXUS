import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, Scan } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PiiDetectionList } from "./pii-detection-list";
import { RedactionLog } from "./redaction-log";

// Local type — generated PIIDetection has optional page_number and PIICategory
// enum, but PiiDetectionList expects required page_number: number.
interface PIIDetection {
  category: string;
  text: string;
  start: number;
  end: number;
  page_number: number;
  confidence: number;
}

interface Props {
  documentId: string;
}

export function RedactionPanel({ documentId }: Props) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const detectQuery = useQuery({
    queryKey: ["pii-detections", documentId],
    queryFn: () =>
      apiClient<PIIDetection[]>({
        url: `/api/v1/documents/${documentId}/pii-detections`,
        method: "GET",
      }),
    enabled: false, // manual trigger
  });

  const redactMutation = useMutation({
    mutationFn: (detections: PIIDetection[]) =>
      apiClient<unknown>({
        url: `/api/v1/documents/${documentId}/redact`,
        method: "POST",
        data: {
          redactions: detections.map((d) => ({
            page_number: d.page_number,
            start: d.start,
            end: d.end,
            reason: `PII: ${d.category}`,
            redaction_type: "pii",
            pii_category: d.category,
          })),
        },
      }),
    onSuccess: () => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["redaction-log", documentId] });
    },
  });

  const detections = detectQuery.data ?? [];
  const selectedDetections = detections.filter((_, i) => selected.has(i));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-4 w-4" />
            PII Detection
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => detectQuery.refetch()}
            disabled={detectQuery.isFetching}
          >
            <Scan className="mr-1.5 h-3.5 w-3.5" />
            {detectQuery.isFetching ? "Scanning..." : "Detect PII"}
          </Button>

          {detections.length > 0 && (
            <>
              <PiiDetectionList
                detections={detections}
                selected={selected}
                onToggle={(index) => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(index)) next.delete(index);
                    else next.add(index);
                    return next;
                  });
                }}
              />

              <div className="flex items-center justify-between pt-2">
                <span className="text-sm text-muted-foreground">
                  {selected.size} of {detections.length} selected
                </span>
                <Button
                  size="sm"
                  disabled={selected.size === 0 || redactMutation.isPending}
                  onClick={() => redactMutation.mutate(selectedDetections)}
                >
                  {redactMutation.isPending
                    ? "Applying..."
                    : `Apply ${selected.size} Redaction${selected.size !== 1 ? "s" : ""}`}
                </Button>
              </div>

              {redactMutation.isSuccess && (
                <p className="text-sm text-green-600">Redactions applied successfully.</p>
              )}
              {redactMutation.isError && (
                <p className="text-sm text-destructive">{redactMutation.error.message}</p>
              )}
            </>
          )}

          {detectQuery.isSuccess && detections.length === 0 && (
            <p className="text-sm text-muted-foreground">No PII detected in this document.</p>
          )}
        </CardContent>
      </Card>

      <RedactionLog documentId={documentId} />
    </div>
  );
}
