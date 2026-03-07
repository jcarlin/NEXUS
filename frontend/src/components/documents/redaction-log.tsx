import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

interface RedactionLogEntry {
  id: string;
  redaction_type: string;
  pii_category: string | null;
  page_number: number | null;
  reason: string;
  created_at: string;
}

interface RedactionLogResponse {
  items: RedactionLogEntry[];
  total: number;
  offset: number;
  limit: number;
}

interface Props {
  documentId: string;
}

export function RedactionLog({ documentId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["redaction-log", documentId],
    queryFn: () =>
      apiClient<RedactionLogResponse>({
        url: `/api/v1/documents/${documentId}/redaction-log`,
        method: "GET",
        params: { limit: 100 },
      }),
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          Redaction Audit Log ({data?.total ?? 0})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : data?.items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No redactions applied yet.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Page</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <Badge variant="outline">{entry.redaction_type}</Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    {entry.pii_category ?? "—"}
                  </TableCell>
                  <TableCell>{entry.page_number ?? "—"}</TableCell>
                  <TableCell className="text-xs max-w-[200px] truncate">
                    {entry.reason}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(entry.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
