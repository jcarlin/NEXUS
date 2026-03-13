import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { DocumentDetail } from "@/types";

const SENTIMENT_KEYS = [
  { key: "sentiment_positive", label: "Positive", color: "bg-green-500" },
  { key: "sentiment_negative", label: "Negative", color: "bg-red-500" },
  { key: "sentiment_pressure", label: "Pressure", color: "bg-orange-500" },
  { key: "sentiment_opportunity", label: "Opportunity", color: "bg-blue-500" },
  { key: "sentiment_rationalization", label: "Rationalization", color: "bg-purple-500" },
  { key: "sentiment_intent", label: "Intent", color: "bg-yellow-500" },
  { key: "sentiment_concealment", label: "Concealment", color: "bg-pink-500" },
] as const;

interface MetadataPanelProps {
  doc: DocumentDetail;
}

export function MetadataPanel({ doc }: MetadataPanelProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Document Info</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Filename" value={doc.filename} />
          <Row label="Type" value={doc.type?.toUpperCase() ?? "—"} />
          <Row label="Pages" value={String(doc.page_count)} />
          <Row label="Chunks" value={String(doc.chunk_count)} />
          <Row label="Entities" value={String(doc.entity_count)} />
          {doc.file_size_bytes && (
            <Row label="Size" value={`${(doc.file_size_bytes / 1024).toFixed(0)} KB`} />
          )}
          <Row label="Created" value={formatDate(doc.created_at)} />
          {doc.bates_begin && doc.bates_end && (
            <Row label="Bates" value={`${doc.bates_begin} – ${doc.bates_end}`} />
          )}
        </CardContent>
      </Card>

      {doc.summary && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground leading-relaxed">{doc.summary}</p>
          </CardContent>
        </Card>
      )}

      {doc.privilege_status && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Privilege</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={doc.privilege_status === "privileged" ? "destructive" : "secondary"}>
              {doc.privilege_status}
            </Badge>
            {doc.privilege_reviewed_at && (
              <p className="mt-1 text-xs text-muted-foreground">
                Reviewed {formatDate(doc.privilege_reviewed_at)}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {doc.message_id && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Email Metadata</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Message ID" value={doc.message_id} />
            {doc.in_reply_to && <Row label="In Reply To" value={doc.in_reply_to} />}
            {doc.thread_position != null && (
              <Row label="Thread Position" value={String(doc.thread_position)} />
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Sentiment Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {SENTIMENT_KEYS.map(({ key, label, color }) => {
            const val = doc[key];
            if (val == null) return null;
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="w-28 text-xs text-muted-foreground">{label}</span>
                <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <div className={`h-full rounded-full ${color}`} style={{ width: `${val * 100}%` }} />
                </div>
                <span className="w-10 text-right text-xs">{(val * 100).toFixed(0)}%</span>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {doc.hot_doc_score != null && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Scoring</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Hot Doc Score" value={doc.hot_doc_score.toFixed(3)} />
            {doc.anomaly_score != null && (
              <Row label="Anomaly Score" value={doc.anomaly_score.toFixed(3)} />
            )}
            {doc.context_gap_score != null && (
              <Row label="Context Gap" value={doc.context_gap_score.toFixed(3)} />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium truncate max-w-[200px]">{value}</span>
    </div>
  );
}
