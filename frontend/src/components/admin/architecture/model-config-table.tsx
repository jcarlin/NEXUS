interface TierConfig {
  tier: string;
  provider_label: string | null;
  provider_type: string | null;
  model: string | null;
}

interface EmbeddingConfig {
  provider: string;
  model: string;
  dimensions: number;
}

interface ModelConfigTableProps {
  tiers: TierConfig[];
  embedding: EmbeddingConfig | null;
}

export function ModelConfigTable({ tiers, embedding }: ModelConfigTableProps) {
  const queryTier = tiers.find((t) => t.tier === "query");
  const analysisTier = tiers.find((t) => t.tier === "analysis");
  const ingestionTier = tiers.find((t) => t.tier === "ingestion");

  const rows = [
    { role: "Query LLM", provider: queryTier?.provider_type, model: queryTier?.model, detail: "Investigation agent, citation verification, follow-ups" },
    { role: "Analysis LLM", provider: analysisTier?.provider_type, model: analysisTier?.model, detail: "Sentiment scoring, relationship extraction, case setup" },
    { role: "Ingestion LLM", provider: ingestionTier?.provider_type, model: ingestionTier?.model, detail: "Summarization, contextual chunks (when enabled)" },
    { role: "Dense Embeddings", provider: embedding?.provider, model: embedding?.model, detail: embedding ? `${embedding.dimensions}d` : "" },
    { role: "Reranker", provider: "sentence-transformers", model: "BAAI/bge-reranker-v2-m3", detail: "Cross-encoder reranking" },
    { role: "NER", provider: "GLiNER", model: "urchade/gliner_multi_pii-v1", detail: "Zero-shot NER, threshold 0.3, CPU" },
  ];

  return (
    <div className="rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Role</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Provider</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Model</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Details</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.role} className="border-b border-border last:border-0">
              <td className="px-4 py-2 font-medium">{row.role}</td>
              <td className="px-4 py-2 text-muted-foreground">{row.provider ?? "—"}</td>
              <td className="px-4 py-2">
                {row.model ? (
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.model}</code>
                ) : "—"}
              </td>
              <td className="px-4 py-2 text-xs text-muted-foreground">{row.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
