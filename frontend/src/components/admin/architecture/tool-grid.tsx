import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ToolDef {
  name: string;
  description: string;
  category: "core" | "analysis" | "disabled";
  flag?: string;
}

const TOOLS: ToolDef[] = [
  // Core Retrieval (always on when agentic pipeline enabled)
  { name: "vector_search", description: "Dense + Sparse RRF hybrid search via Qdrant", category: "core" },
  { name: "graph_query", description: "Neo4j entity relationship traversal", category: "core" },
  { name: "temporal_search", description: "Date-range scoped semantic search", category: "core" },
  { name: "entity_lookup", description: "Entity resolution with case context alias map", category: "core" },
  { name: "document_retrieval", description: "Fetch all chunks for a document (up to 50)", category: "core" },
  { name: "case_context", description: "Access case claims, parties, terms, timeline", category: "core" },
  // Analysis
  { name: "sentiment_search", description: "Search by 7 sentiment dimensions (pressure, concealment, etc.)", category: "analysis" },
  { name: "hot_doc_search", description: "Risk-ranked document discovery by hot_doc_score", category: "analysis" },
  { name: "context_gap_search", description: "Find emails with missing context or attachments", category: "analysis" },
  { name: "communication_matrix", description: "Sender-recipient communication pattern analysis", category: "analysis" },
  { name: "topic_cluster", description: "BERTopic unsupervised topic clustering", category: "analysis", flag: "enable_topic_clustering" },
  { name: "network_analysis", description: "Neo4j GDS centrality (degree, PageRank, betweenness)", category: "analysis", flag: "enable_graph_centrality" },
  // Flag-gated (potentially disabled)
  { name: "decompose_query", description: "Multi-part question decomposition + parallel retrieval", category: "disabled", flag: "enable_question_decomposition" },
  { name: "cypher_query", description: "Natural language to read-only Cypher queries", category: "disabled", flag: "enable_text_to_cypher" },
  { name: "structured_query", description: "Natural language to read-only SQL queries", category: "disabled", flag: "enable_text_to_sql" },
  { name: "get_community_context", description: "GraphRAG Louvain community context lookup", category: "disabled", flag: "enable_graphrag_communities" },
  { name: "ask_user", description: "Human-in-the-loop clarification via LangGraph interrupt", category: "disabled", flag: "enable_agent_clarification" },
];

const categoryStyles = {
  core: "border-l-blue-500",
  analysis: "border-l-amber-500",
  disabled: "border-l-muted-foreground/40",
};

interface ToolGridProps {
  flagMap: Map<string, boolean>;
}

export function ToolGrid({ flagMap }: ToolGridProps) {
  const resolveEnabled = (tool: ToolDef) => {
    if (!tool.flag) return true;
    return flagMap.get(tool.flag) ?? false;
  };

  const categories = [
    { key: "core" as const, label: "Core Retrieval" },
    { key: "analysis" as const, label: "Analysis" },
    { key: "disabled" as const, label: "Advanced / Flag-Gated" },
  ];

  return (
    <div className="mt-3 space-y-3">
      {categories.map(({ key, label }) => {
        const tools = TOOLS.filter((t) => t.category === key);
        if (tools.length === 0) return null;
        return (
          <div key={key}>
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {tools.map((tool) => {
                const enabled = resolveEnabled(tool);
                return (
                  <Tooltip key={tool.name}>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          "cursor-help rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-[11px] transition-all duration-150",
                          "border-l-[3px] hover:bg-muted/60 hover:shadow-xs",
                          enabled ? categoryStyles[tool.category] : "border-l-muted-foreground/30",
                          !enabled && "border-dashed opacity-45 hover:opacity-55",
                        )}
                      >
                        <span className="font-semibold">{tool.name}</span>
                        {!enabled && (
                          <span className="ml-1.5 text-[9px] text-muted-foreground">(off)</span>
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <p className="text-xs">{tool.description}</p>
                      {tool.flag && (
                        <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                          {tool.flag}: {enabled ? "true" : "false"}
                        </p>
                      )}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
