import { PipelineNode } from "./pipeline-node";

/* ------------------------------------------------------------------ */
/*  PostgreSQL table groups                                            */
/* ------------------------------------------------------------------ */

interface TableGroup {
  name: string;
  tables: string[];
  description: string;
  keyColumns?: { table: string; columns: string[] }[];
}

const PG_TABLE_GROUPS: TableGroup[] = [
  {
    name: "Core",
    tables: ["jobs", "documents", "chat_messages", "case_matters"],
    description: "Primary entities for document processing, conversations, and case organization",
    keyColumns: [
      {
        table: "documents",
        columns: [
          "id", "job_id", "matter_id", "filename", "document_type",
          "page_count", "chunk_count", "entity_count", "minio_path",
          "file_size_bytes", "content_hash", "privilege_status",
          "message_id", "thread_id", "sentiment_*", "hot_doc_score", "summary",
        ],
      },
    ],
  },
  {
    name: "Auth",
    tables: ["users", "user_case_matters"],
    description: "Authentication, RBAC (4 roles), and user-matter access control",
  },
  {
    name: "Audit",
    tables: ["audit_log", "ai_audit_log", "agent_audit_log"],
    description: "Append-only audit trail for API requests, LLM calls, and agent actions",
  },
  {
    name: "EDRM",
    tables: ["edrm_import_log", "communication_pairs"],
    description: "Electronic Discovery Reference Model imports and communication pair analytics",
  },
  {
    name: "Case Intelligence",
    tables: ["case_contexts", "case_claims", "case_parties", "case_defined_terms", "investigation_sessions"],
    description: "AI-extracted case context: claims, parties, defined terms, and investigation sessions",
  },
  {
    name: "Organization",
    tables: ["org_chart_entries"],
    description: "Inferred/manual organizational hierarchy for entity resolution",
  },
  {
    name: "Annotations & Production",
    tables: ["annotations", "production_sets", "production_set_documents", "export_jobs"],
    description: "Document annotations, Bates-numbered production sets, and export tracking",
  },
  {
    name: "Redaction",
    tables: ["redactions"],
    description: "Append-only redaction records (manual, PII-auto, privilege) with audit hashes",
  },
  {
    name: "Evaluation",
    tables: ["evaluation_dataset_items", "evaluation_runs"],
    description: "Ground-truth Q&A datasets and scored RAG evaluation runs",
  },
  {
    name: "Datasets",
    tables: ["datasets", "dataset_documents", "document_tags", "dataset_access"],
    description: "Hierarchical dataset tree, document membership, tagging, and per-dataset ACLs",
  },
  {
    name: "Google Drive",
    tables: ["google_drive_connections", "google_drive_sync_state"],
    description: "Encrypted OAuth tokens and incremental sync state",
  },
  {
    name: "Memos",
    tables: ["memos"],
    description: "AI-generated and user-authored investigation memos from chat threads",
  },
  {
    name: "LLM Config",
    tables: ["llm_providers", "llm_tier_config"],
    description: "Runtime provider registry and tier-based model routing (query/analysis/ingestion)",
  },
  {
    name: "Feature Flags",
    tables: ["feature_flag_overrides"],
    description: "Admin-toggled runtime feature flag overrides",
  },
  {
    name: "Retention",
    tables: ["retention_policies"],
    description: "Per-matter data retention policies with purge scheduling",
  },
  {
    name: "Background",
    tables: ["bulk_import_jobs"],
    description: "Bulk import orchestration with adapter type, progress, and error state",
  },
  {
    name: "Quality",
    tables: ["query_quality_metrics", "community_summaries"],
    description: "Production query quality monitoring and GraphRAG community detection",
  },
];

/* ------------------------------------------------------------------ */
/*  Qdrant vector collections                                          */
/* ------------------------------------------------------------------ */

interface QdrantVector {
  name: string;
  type: string;
  dimensions: string;
  distance: string;
  note?: string;
}

interface QdrantCollection {
  name: string;
  vectors: QdrantVector[];
  payload: string[];
  notes?: string;
}

const QDRANT_COLLECTIONS: QdrantCollection[] = [
  {
    name: "nexus_text",
    vectors: [
      { name: "dense", type: "Dense", dimensions: "1024d", distance: "COSINE" },
      { name: "sparse", type: "Sparse", dimensions: "variable", distance: "BM42", note: "flag-gated" },
      { name: "summary", type: "Dense", dimensions: "1024d", distance: "COSINE", note: "multi-representation" },
    ],
    payload: ["doc_id", "chunk_id", "page_number", "chunk_index", "privilege_status", "matter_id"],
  },
  {
    name: "nexus_visual",
    vectors: [
      { name: "patches", type: "Multi-vector MaxSim", dimensions: "N\u00d7128d", distance: "COSINE", note: "ColQwen2.5" },
    ],
    payload: ["doc_id", "page_number", "matter_id"],
    notes: "HNSW disabled \u2014 reranking-only collection",
  },
];

/* ------------------------------------------------------------------ */
/*  Neo4j graph schema                                                 */
/* ------------------------------------------------------------------ */

interface Neo4jGroup<T> {
  category: string;
  items: T[];
}

const NEO4J_NODE_GROUPS: Neo4jGroup<string>[] = [
  { category: "Core", items: ["Entity", "Document", "Chunk", "Topic"] },
  { category: "Entity subtypes", items: ["Person", "Organization", "Location", "Event", "Financial", "LegalReference", "ContactInfo"] },
  { category: "Communication", items: ["Email"] },
];

const NEO4J_REL_GROUPS: Neo4jGroup<string>[] = [
  { category: "Structural", items: ["PART_OF", "SOURCED_FROM", "MENTIONED_IN"] },
  { category: "Communication", items: ["SENT", "SENT_TO", "CC", "BCC"] },
  { category: "Organizational", items: ["MANAGES", "HAS_ROLE", "MEMBER_OF", "BOARD_MEMBER", "REPORTS_TO"] },
  { category: "Semantic", items: ["CO_OCCURS", "RELATED_TO", "DISCUSSES", "ALIAS_OF"] },
];

const NEO4J_CONSTRAINTS = [
  "Entity(name, type, matter_id)",
  "Document(id)",
  "Chunk(id)",
  "Email(id)",
  "Topic(name, matter_id)",
];

/* ------------------------------------------------------------------ */
/*  Section header                                                     */
/* ------------------------------------------------------------------ */

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/5 px-4 py-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
        {title}
      </span>
      <span className="text-xs text-muted-foreground">{subtitle}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DataStores() {
  const totalTables = PG_TABLE_GROUPS.reduce((sum, g) => sum + g.tables.length, 0);
  const totalNodes = NEO4J_NODE_GROUPS.reduce((sum, g) => sum + g.items.length, 0);
  const totalRels = NEO4J_REL_GROUPS.reduce((sum, g) => sum + g.items.length, 0);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-10">
      {/* ── PostgreSQL ── */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="PostgreSQL \u2014 Relational Store"
          subtitle={`${totalTables} tables across ${PG_TABLE_GROUPS.length} domains`}
        />
        <div className="grid grid-cols-2 gap-3">
          {PG_TABLE_GROUPS.map((group) => (
            <PipelineNode key={group.name} title={group.name} variant="store">
              <p>{group.description}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {group.tables.map((t) => (
                  <code key={t} className="rounded bg-muted px-1 text-[11px]">{t}</code>
                ))}
              </div>
              {group.keyColumns?.map((kc) => (
                <div key={kc.table} className="mt-2 border-t border-border/50 pt-2">
                  <span className="text-[11px] font-medium text-foreground">
                    {kc.table} key columns:
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {kc.columns.map((col) => (
                      <code key={col} className="rounded bg-muted px-1 text-[10px]">{col}</code>
                    ))}
                  </div>
                </div>
              ))}
            </PipelineNode>
          ))}
        </div>
      </section>

      {/* ── Qdrant ── */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="Qdrant \u2014 Vector Store"
          subtitle={`${QDRANT_COLLECTIONS.length} collections, hybrid retrieval`}
        />
        <div className="flex flex-col gap-3">
          {QDRANT_COLLECTIONS.map((col) => (
            <PipelineNode key={col.name} title={col.name} variant="store">
              <span className="font-medium text-foreground">Vectors:</span>
              {col.vectors.map((v) => (
                <div key={v.name} className="ml-2">
                  &bull; <code className="rounded bg-muted px-1 text-[11px]">{v.name}</code>
                  {" "}&mdash; {v.type}, {v.dimensions}, {v.distance}
                  {v.note && <span className="ml-1 text-[10px]">({v.note})</span>}
                </div>
              ))}
              <div className="mt-2">
                <span className="font-medium text-foreground">Payload:</span>{" "}
                {col.payload.map((p, i) => (
                  <span key={p}>
                    <code className="rounded bg-muted px-1 text-[11px]">{p}</code>
                    {i < col.payload.length - 1 && ", "}
                  </span>
                ))}
              </div>
              {col.notes && (
                <div className="mt-1 text-[10px]">{col.notes}</div>
              )}
            </PipelineNode>
          ))}
        </div>
      </section>

      {/* ── Neo4j ── */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="Neo4j \u2014 Knowledge Graph"
          subtitle={`${totalNodes} node types, ${totalRels} relationship types`}
        />
        <div className="grid grid-cols-2 gap-3">
          <PipelineNode title={`Node Types (${totalNodes})`} variant="store">
            {NEO4J_NODE_GROUPS.map((group) => (
              <div key={group.category} className="mt-1 first:mt-0">
                <span className="font-medium text-foreground">{group.category}:</span>{" "}
                {group.items.map((label, i) => (
                  <span key={label}>
                    <code className="rounded bg-muted px-1 text-[11px]">:{label}</code>
                    {i < group.items.length - 1 && " "}
                  </span>
                ))}
              </div>
            ))}
          </PipelineNode>
          <PipelineNode title={`Relationship Types (${totalRels})`} variant="store">
            {NEO4J_REL_GROUPS.map((group) => (
              <div key={group.category} className="mt-1 first:mt-0">
                <span className="font-medium text-foreground">{group.category}:</span>{" "}
                {group.items.map((rel, i) => (
                  <span key={rel}>
                    <code className="rounded bg-muted px-1 text-[11px]">{rel}</code>
                    {i < group.items.length - 1 && " "}
                  </span>
                ))}
              </div>
            ))}
          </PipelineNode>
        </div>
        <PipelineNode title="Constraints & Indexes" variant="store">
          <span className="font-medium text-foreground">Uniqueness constraints:</span>
          {NEO4J_CONSTRAINTS.map((c) => (
            <div key={c} className="ml-2">
              &bull; <code className="rounded bg-muted px-1 text-[11px]">{c}</code>
            </div>
          ))}
        </PipelineNode>
      </section>

      {/* ── Cross-Store Links ── */}
      <section className="flex flex-col gap-4">
        <SectionHeader
          title="Cross-Store Links"
          subtitle="How the three stores connect"
        />
        <PipelineNode title="Data Flow & Scoping" variant="store">
          <div className="space-y-1">
            <div>
              &bull; <code className="rounded bg-muted px-1 text-[11px]">documents.id</code>
              {" "}&rarr; Qdrant <code className="rounded bg-muted px-1 text-[11px]">doc_id</code> payload
              {" "}&rarr; Neo4j <code className="rounded bg-muted px-1 text-[11px]">Document.id</code>
            </div>
            <div>
              &bull; <code className="rounded bg-muted px-1 text-[11px]">matter_id</code>
              {" "}scoped across all three stores (multi-tenant isolation)
            </div>
            <div>
              &bull; Qdrant point ID stored on Neo4j <code className="rounded bg-muted px-1 text-[11px]">Chunk.qdrant_point_id</code> for retrieval chain
            </div>
            <div>
              &bull; <code className="rounded bg-muted px-1 text-[11px]">case_parties.entity_id</code>
              {" "}&rarr; Neo4j <code className="rounded bg-muted px-1 text-[11px]">Entity</code> nodes (case intelligence linkage)
            </div>
            <div>
              &bull; Privilege status synced: PG <code className="rounded bg-muted px-1 text-[11px]">documents.privilege_status</code>
              {" "}&rarr; Qdrant payload filter &rarr; Neo4j <code className="rounded bg-muted px-1 text-[11px]">Document.privilege_status</code>
            </div>
          </div>
        </PipelineNode>
      </section>
    </div>
  );
}
