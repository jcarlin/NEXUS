import type { Edge } from "@xyflow/react";
import { MarkerType } from "@xyflow/react";
import type {
  TableNodeType,
  CollectionNodeType,
  GraphLabelNodeType,
  StoreGroupType,
} from "./schema-nodes";

/* ================================================================== */
/*  Layout constants                                                   */
/* ================================================================== */

const PAD = 24;
const PAD_TOP = 44;
const TBL_W = 170;
const TBL_H_SM = 100;
const TBL_H_MD = 130;
const TBL_H_LG = 180;
const COL_GAP = 28;
const ROW_GAP = 24;

/* ── PostgreSQL group ─────────────────────────────────────────────── */

const PG_X = 0;
const PG_Y = 0;
const PG_COLS = 6;
const PG_ROWS = 6;
const PG_W = PAD * 2 + PG_COLS * TBL_W + (PG_COLS - 1) * COL_GAP;
const PG_H = PAD_TOP + 20 + PG_ROWS * TBL_H_MD + (PG_ROWS - 1) * ROW_GAP + PAD;

const pgX = (col: number) => PG_X + PAD + col * (TBL_W + COL_GAP);
const pgY = (row: number) => PG_Y + PAD_TOP + 20 + row * (TBL_H_MD + ROW_GAP);

/* ── Qdrant group ─────────────────────────────────────────────────── */

const QD_Y = PG_Y + PG_H + 40;
const QD_W = PG_W;
const QD_H = PAD_TOP + TBL_H_LG + PAD + 20;
const qdX = (col: number) => PAD + col * 300;

/* ── Neo4j group ──────────────────────────────────────────────────── */

const N4_Y = QD_Y + QD_H + 40;
const N4_W = PG_W;
const N4_H = PAD_TOP + 2 * TBL_H_SM + ROW_GAP + PAD + 20;
const n4X = (col: number) => PAD + col * (TBL_W + COL_GAP);
const n4Y = (row: number) => PAD_TOP + 20 + row * (TBL_H_SM + ROW_GAP);

/* ================================================================== */
/*  Store groups (swim lanes)                                          */
/* ================================================================== */

export const storeGroups: StoreGroupType[] = [
  {
    id: "g-pg",
    type: "storeGroup",
    position: { x: PG_X, y: PG_Y },
    style: { width: PG_W, height: PG_H },
    data: { label: "PostgreSQL", color: "blue", subtitle: "36 tables \u2014 relational store" },
  },
  {
    id: "g-qdrant",
    type: "storeGroup",
    position: { x: PG_X, y: QD_Y },
    style: { width: QD_W, height: QD_H },
    data: { label: "Qdrant", color: "emerald", subtitle: "2 collections \u2014 vector store" },
  },
  {
    id: "g-neo4j",
    type: "storeGroup",
    position: { x: PG_X, y: N4_Y },
    style: { width: N4_W, height: N4_H },
    data: { label: "Neo4j", color: "purple", subtitle: "13 node types, 14 relationship types \u2014 knowledge graph" },
  },
];

/* ================================================================== */
/*  PostgreSQL table nodes                                             */
/* ================================================================== */

export const tableNodes: TableNodeType[] = [
  /* ── Row 0: Central entities ─────────────────────────────────────── */
  {
    id: "t-case_matters",
    type: "table",
    position: { x: pgX(0), y: pgY(0) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "case_matters",
      domain: "core",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "name", type: "col" },
        { name: "description", type: "col" },
        { name: "created_at", type: "col" },
      ],
    },
  },
  {
    id: "t-jobs",
    type: "table",
    position: { x: pgX(1), y: pgY(0) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "jobs",
      domain: "ingestion",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "status", type: "idx" },
        { name: "stage, error", type: "col" },
        { name: "error_category", type: "idx" },
        { name: "retry_count", type: "col" },
      ],
    },
  },
  {
    id: "t-documents",
    type: "table",
    position: { x: pgX(2), y: pgY(0) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "documents",
      domain: "core",
      rowHint: "50K+",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "job_id \u2192 jobs", type: "fk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "filename, doc_type", type: "col" },
        { name: "privilege_status", type: "idx" },
        { name: "hot_doc_score", type: "col" },
      ],
    },
  },
  {
    id: "t-users",
    type: "table",
    position: { x: pgX(4), y: pgY(0) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "users",
      domain: "auth",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "email (unique)", type: "idx" },
        { name: "password_hash", type: "col" },
        { name: "role", type: "col" },
        { name: "is_active", type: "col" },
      ],
    },
  },
  {
    id: "t-user_case_matters",
    type: "table",
    position: { x: pgX(5), y: pgY(0) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "user_case_matters",
      domain: "auth",
      columns: [
        { name: "user_id \u2192 users", type: "fk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "assigned_at", type: "col" },
      ],
    },
  },

  /* ── Row 1: Chat & case intelligence ─────────────────────────────── */
  {
    id: "t-chat_messages",
    type: "table",
    position: { x: pgX(0), y: pgY(1) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "chat_messages",
      domain: "query",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "thread_id", type: "idx" },
        { name: "role, content", type: "col" },
      ],
    },
  },
  {
    id: "t-case_contexts",
    type: "table",
    position: { x: pgX(1), y: pgY(1) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "case_contexts",
      domain: "cases",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "anchor_doc_id", type: "fk" },
        { name: "summary", type: "col" },
      ],
    },
  },
  {
    id: "t-case_claims",
    type: "table",
    position: { x: pgX(2), y: pgY(1) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "case_claims",
      domain: "cases",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "context_id \u2192 case_contexts", type: "fk" },
        { name: "description", type: "col" },
        { name: "category", type: "col" },
      ],
    },
  },
  {
    id: "t-case_parties",
    type: "table",
    position: { x: pgX(3), y: pgY(1) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "case_parties",
      domain: "cases",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "context_id \u2192 case_contexts", type: "fk" },
        { name: "name, role", type: "col" },
        { name: "entity_id \u2192 Neo4j", type: "fk" },
      ],
    },
  },
  {
    id: "t-investigation_sessions",
    type: "table",
    position: { x: pgX(4), y: pgY(1) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "investigation_sessions",
      domain: "cases",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "thread_id", type: "col" },
        { name: "hypothesis", type: "col" },
      ],
    },
  },

  /* ── Row 2: Documents ecosystem ──────────────────────────────────── */
  {
    id: "t-annotations",
    type: "table",
    position: { x: pgX(0), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "annotations",
      domain: "production",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "document_id \u2192 documents", type: "fk" },
        { name: "page, coordinates", type: "col" },
        { name: "content, label", type: "col" },
      ],
    },
  },
  {
    id: "t-redactions",
    type: "table",
    position: { x: pgX(1), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "redactions",
      domain: "production",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "document_id \u2192 documents", type: "fk" },
        { name: "page, coordinates", type: "col" },
        { name: "reason, type", type: "col" },
      ],
    },
  },
  {
    id: "t-datasets",
    type: "table",
    position: { x: pgX(2), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "datasets",
      domain: "datasets",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "parent_id \u2192 self", type: "fk" },
        { name: "name, description", type: "col" },
      ],
    },
  },
  {
    id: "t-dataset_documents",
    type: "table",
    position: { x: pgX(3), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "dataset_documents",
      domain: "datasets",
      columns: [
        { name: "dataset_id \u2192 datasets", type: "fk" },
        { name: "document_id \u2192 documents", type: "fk" },
      ],
    },
  },
  {
    id: "t-document_tags",
    type: "table",
    position: { x: pgX(4), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "document_tags",
      domain: "datasets",
      columns: [
        { name: "document_id \u2192 documents", type: "fk" },
        { name: "tag_name", type: "idx" },
        { name: "created_by \u2192 users", type: "fk" },
      ],
    },
  },
  {
    id: "t-memos",
    type: "table",
    position: { x: pgX(5), y: pgY(2) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "memos",
      domain: "query",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "created_by \u2192 users", type: "fk" },
        { name: "title, content", type: "col" },
      ],
    },
  },

  /* ── Row 3: Production & exports ─────────────────────────────────── */
  {
    id: "t-production_sets",
    type: "table",
    position: { x: pgX(0), y: pgY(3) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "production_sets",
      domain: "production",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "name, bates_prefix", type: "col" },
      ],
    },
  },
  {
    id: "t-prod_set_docs",
    type: "table",
    position: { x: pgX(1), y: pgY(3) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "production_set_documents",
      domain: "production",
      columns: [
        { name: "set_id \u2192 production_sets", type: "fk" },
        { name: "document_id \u2192 documents", type: "fk" },
        { name: "bates_number", type: "idx" },
      ],
    },
  },
  {
    id: "t-export_jobs",
    type: "table",
    position: { x: pgX(2), y: pgY(3) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "export_jobs",
      domain: "production",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "status, format", type: "col" },
        { name: "result_path", type: "col" },
      ],
    },
  },
  {
    id: "t-edrm_import_log",
    type: "table",
    position: { x: pgX(3), y: pgY(3) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "edrm_import_log",
      domain: "edrm",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "filename, status", type: "col" },
      ],
    },
  },
  {
    id: "t-communication_pairs",
    type: "table",
    position: { x: pgX(4), y: pgY(3) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "communication_pairs",
      domain: "edrm",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "sender, recipient", type: "col" },
        { name: "count, direction", type: "col" },
      ],
    },
  },

  /* ── Row 4: Audit & quality ──────────────────────────────────────── */
  {
    id: "t-audit_log",
    type: "table",
    position: { x: pgX(0), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "audit_log",
      domain: "audit",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "user_id, action", type: "col" },
        { name: "resource, matter_id", type: "col" },
        { name: "ip_address", type: "col" },
      ],
      rowHint: "append-only",
    },
  },
  {
    id: "t-ai_audit_log",
    type: "table",
    position: { x: pgX(1), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "ai_audit_log",
      domain: "audit",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "prompt_hash", type: "idx" },
        { name: "provider, model", type: "col" },
        { name: "tokens_in, tokens_out", type: "col" },
      ],
      rowHint: "append-only",
    },
  },
  {
    id: "t-agent_audit_log",
    type: "table",
    position: { x: pgX(2), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "agent_audit_log",
      domain: "audit",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "agent_name, tool", type: "col" },
        { name: "matter_id", type: "col" },
        { name: "latency_ms", type: "col" },
      ],
      rowHint: "append-only",
    },
  },
  {
    id: "t-eval_items",
    type: "table",
    position: { x: pgX(3), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "evaluation_dataset_items",
      domain: "analytics",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "question, answer", type: "col" },
        { name: "source_doc_ids", type: "col" },
        { name: "dataset_type", type: "col" },
      ],
    },
  },
  {
    id: "t-eval_runs",
    type: "table",
    position: { x: pgX(4), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "evaluation_runs",
      domain: "analytics",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "config", type: "col" },
        { name: "mrr, recall, ndcg", type: "col" },
        { name: "faithfulness", type: "col" },
      ],
    },
  },
  {
    id: "t-query_quality",
    type: "table",
    position: { x: pgX(5), y: pgY(4) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "query_quality_metrics",
      domain: "analytics",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "query_hash", type: "idx" },
        { name: "relevance, faithfulness", type: "col" },
        { name: "sampled_at", type: "col" },
      ],
    },
  },

  /* ── Row 5: Config & infrastructure ──────────────────────────────── */
  {
    id: "t-llm_providers",
    type: "table",
    position: { x: pgX(0), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "llm_providers",
      domain: "config",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "provider, model", type: "col" },
        { name: "base_url", type: "col" },
        { name: "is_active", type: "col" },
      ],
    },
  },
  {
    id: "t-llm_tier_config",
    type: "table",
    position: { x: pgX(1), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "llm_tier_config",
      domain: "config",
      columns: [
        { name: "tier (pk)", type: "pk" },
        { name: "provider_id \u2192 llm_providers", type: "fk" },
      ],
    },
  },
  {
    id: "t-feature_flag_overrides",
    type: "table",
    position: { x: pgX(2), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "feature_flag_overrides",
      domain: "config",
      columns: [
        { name: "flag_name (pk)", type: "pk" },
        { name: "enabled", type: "col" },
        { name: "updated_at", type: "col" },
      ],
    },
  },
  {
    id: "t-retention_policies",
    type: "table",
    position: { x: pgX(3), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "retention_policies",
      domain: "config",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "retain_days", type: "col" },
      ],
    },
  },
  {
    id: "t-bulk_import_jobs",
    type: "table",
    position: { x: pgX(4), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "bulk_import_jobs",
      domain: "ingestion",
      columns: [
        { name: "id (uuid)", type: "pk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
        { name: "adapter_type", type: "col" },
        { name: "progress, status", type: "col" },
      ],
    },
  },
  {
    id: "t-gdrive",
    type: "table",
    position: { x: pgX(5), y: pgY(5) },
    parentId: "g-pg",
    extent: "parent",
    data: {
      label: "google_drive_*",
      domain: "config",
      columns: [
        { name: "connections (OAuth tokens)", type: "col" },
        { name: "sync_state (incremental)", type: "col" },
        { name: "user_id \u2192 users", type: "fk" },
        { name: "matter_id \u2192 case_matters", type: "fk" },
      ],
    },
  },
];

/* ================================================================== */
/*  Qdrant collection nodes                                            */
/* ================================================================== */

export const collectionNodes: CollectionNodeType[] = [
  {
    id: "q-nexus_text",
    type: "collection",
    position: { x: qdX(0), y: PAD_TOP + 10 },
    parentId: "g-qdrant",
    extent: "parent",
    data: {
      label: "nexus_text",
      vectors: [
        { name: "dense", dims: "1024d", distance: "COSINE" },
        { name: "sparse", dims: "variable", distance: "BM42", note: "flag-gated" },
        { name: "summary", dims: "1024d", distance: "COSINE", note: "multi-repr" },
      ],
      payload: ["doc_id", "chunk_id", "page_number", "chunk_index", "privilege_status", "matter_id"],
    },
  },
  {
    id: "q-nexus_visual",
    type: "collection",
    position: { x: qdX(1), y: PAD_TOP + 10 },
    parentId: "g-qdrant",
    extent: "parent",
    data: {
      label: "nexus_visual",
      vectors: [
        { name: "patches", dims: "N\u00d7128d", distance: "COSINE", note: "ColQwen2.5 MaxSim" },
      ],
      payload: ["doc_id", "page_number", "matter_id"],
      note: "HNSW disabled \u2014 reranking-only",
    },
  },
];

/* ================================================================== */
/*  Neo4j graph label nodes                                            */
/* ================================================================== */

export const graphLabelNodes: GraphLabelNodeType[] = [
  /* ── Node types ──────────────────────────────────────────────────── */
  {
    id: "n4-entity",
    type: "graphLabel",
    position: { x: n4X(0), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Entity",
      variant: "node",
      properties: ["name", "type", "matter_id", "mention_count"],
    },
  },
  {
    id: "n4-person",
    type: "graphLabel",
    position: { x: n4X(1), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Person",
      variant: "node",
      properties: ["email_address", "org"],
    },
  },
  {
    id: "n4-organization",
    type: "graphLabel",
    position: { x: n4X(2), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: { label: "Organization", variant: "node" },
  },
  {
    id: "n4-document",
    type: "graphLabel",
    position: { x: n4X(3), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Document",
      variant: "node",
      properties: ["id", "matter_id", "privilege_status"],
    },
  },
  {
    id: "n4-chunk",
    type: "graphLabel",
    position: { x: n4X(4), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Chunk",
      variant: "node",
      properties: ["id", "qdrant_point_id"],
    },
  },
  {
    id: "n4-email",
    type: "graphLabel",
    position: { x: n4X(5), y: n4Y(0) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Email",
      variant: "node",
      properties: ["id", "subject", "date"],
    },
  },

  /* ── Relationship groups ─────────────────────────────────────────── */
  {
    id: "n4-rel-structural",
    type: "graphLabel",
    position: { x: n4X(0), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Structural",
      variant: "relationship",
      properties: ["PART_OF", "SOURCED_FROM", "MENTIONED_IN", "EXTRACTED_FROM"],
    },
  },
  {
    id: "n4-rel-comms",
    type: "graphLabel",
    position: { x: n4X(1), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Communication",
      variant: "relationship",
      properties: ["SENT", "SENT_TO", "CC", "BCC"],
    },
  },
  {
    id: "n4-rel-org",
    type: "graphLabel",
    position: { x: n4X(2), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Organizational",
      variant: "relationship",
      properties: ["MANAGES", "HAS_ROLE", "MEMBER_OF", "REPORTS_TO"],
    },
  },
  {
    id: "n4-rel-semantic",
    type: "graphLabel",
    position: { x: n4X(3), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Semantic",
      variant: "relationship",
      properties: ["CO_OCCURS", "RELATED_TO", "DISCUSSES", "ALIAS_OF"],
    },
  },
  {
    id: "n4-topic",
    type: "graphLabel",
    position: { x: n4X(4), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Topic",
      variant: "node",
      properties: ["name", "matter_id", "keywords"],
    },
  },
  {
    id: "n4-location",
    type: "graphLabel",
    position: { x: n4X(5), y: n4Y(1) },
    parentId: "g-neo4j",
    extent: "parent",
    data: {
      label: "Location / Event / ...",
      variant: "node",
      properties: ["Entity subtypes via labels"],
    },
  },
];

/* ================================================================== */
/*  All nodes combined                                                 */
/* ================================================================== */

export const allSchemaNodes = [
  ...storeGroups,
  ...tableNodes,
  ...collectionNodes,
  ...graphLabelNodes,
];

/* ================================================================== */
/*  Edges                                                              */
/* ================================================================== */

const fkEdge = (id: string, source: string, target: string, label?: string): Edge => ({
  id,
  source,
  target,
  sourceHandle: "right",
  targetHandle: "left",
  type: "smoothstep",
  animated: false,
  style: { stroke: "var(--color-blue-400)", strokeWidth: 1.2, opacity: 0.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "var(--color-blue-400)", width: 12, height: 12 },
  label,
  labelStyle: { fontSize: 9, fill: "var(--color-muted-foreground)" },
});

const crossStoreEdge = (id: string, source: string, target: string, label: string): Edge => ({
  id,
  source,
  target,
  type: "smoothstep",
  animated: true,
  style: { stroke: "var(--color-amber-500)", strokeWidth: 1.5, strokeDasharray: "6 3", opacity: 0.7 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "var(--color-amber-500)", width: 14, height: 14 },
  label,
  labelStyle: { fontSize: 9, fill: "var(--color-amber-600)", fontWeight: 600 },
  labelBgStyle: { fill: "var(--color-card)", fillOpacity: 0.9 },
  labelBgPadding: [4, 2] as [number, number],
});

const graphEdge = (id: string, source: string, target: string, label?: string): Edge => ({
  id,
  source,
  target,
  sourceHandle: "right",
  targetHandle: "left",
  type: "smoothstep",
  style: { stroke: "var(--color-purple-400)", strokeWidth: 1.2, opacity: 0.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "var(--color-purple-400)", width: 12, height: 12 },
  label,
  labelStyle: { fontSize: 8, fill: "var(--color-muted-foreground)" },
});

export const allSchemaEdges: Edge[] = [
  /* ── PostgreSQL FK relationships ─────────────────────────────────── */
  // Core
  fkEdge("fk-jobs-matters", "t-jobs", "t-case_matters", "matter_id"),
  fkEdge("fk-docs-jobs", "t-documents", "t-jobs", "job_id"),
  fkEdge("fk-docs-matters", "t-documents", "t-case_matters"),
  fkEdge("fk-ucm-users", "t-user_case_matters", "t-users", "user_id"),
  fkEdge("fk-ucm-matters", "t-user_case_matters", "t-case_matters"),

  // Chat & case intelligence
  fkEdge("fk-chat-matters", "t-chat_messages", "t-case_matters"),
  fkEdge("fk-ctx-matters", "t-case_contexts", "t-case_matters"),
  fkEdge("fk-claims-ctx", "t-case_claims", "t-case_contexts", "context_id"),
  fkEdge("fk-parties-ctx", "t-case_parties", "t-case_contexts"),
  fkEdge("fk-inv-matters", "t-investigation_sessions", "t-case_matters"),

  // Documents ecosystem
  fkEdge("fk-ann-docs", "t-annotations", "t-documents", "document_id"),
  fkEdge("fk-red-docs", "t-redactions", "t-documents"),
  fkEdge("fk-ds-matters", "t-datasets", "t-case_matters"),
  fkEdge("fk-dsdoc-ds", "t-dataset_documents", "t-datasets", "dataset_id"),
  fkEdge("fk-dsdoc-docs", "t-dataset_documents", "t-documents"),
  fkEdge("fk-tags-docs", "t-document_tags", "t-documents"),
  fkEdge("fk-memos-matters", "t-memos", "t-case_matters"),
  fkEdge("fk-memos-users", "t-memos", "t-users"),

  // Production
  fkEdge("fk-prod-matters", "t-production_sets", "t-case_matters"),
  fkEdge("fk-psd-prod", "t-prod_set_docs", "t-production_sets"),
  fkEdge("fk-psd-docs", "t-prod_set_docs", "t-documents"),
  fkEdge("fk-export-matters", "t-export_jobs", "t-case_matters"),

  // Config
  fkEdge("fk-tier-prov", "t-llm_tier_config", "t-llm_providers", "provider_id"),
  fkEdge("fk-ret-matters", "t-retention_policies", "t-case_matters"),
  fkEdge("fk-bulk-matters", "t-bulk_import_jobs", "t-case_matters"),

  /* ── Cross-store links ───────────────────────────────────────────── */
  crossStoreEdge("xs-docs-qdrant", "t-documents", "q-nexus_text", "documents.id \u2192 doc_id"),
  crossStoreEdge("xs-docs-neo4j", "t-documents", "n4-document", "documents.id \u2192 Document.id"),
  crossStoreEdge("xs-qdrant-neo4j", "q-nexus_text", "n4-chunk", "chunk \u2192 Chunk.qdrant_point_id"),
  crossStoreEdge("xs-parties-neo4j", "t-case_parties", "n4-entity", "entity_id \u2192 Entity"),
  crossStoreEdge("xs-docs-visual", "t-documents", "q-nexus_visual", "page images"),

  /* ── Neo4j graph relationships ───────────────────────────────────── */
  graphEdge("g-entity-person", "n4-entity", "n4-person", ":Person label"),
  graphEdge("g-entity-org", "n4-entity", "n4-organization", ":Organization"),
  graphEdge("g-chunk-doc", "n4-chunk", "n4-document", "PART_OF"),
  graphEdge("g-entity-chunk", "n4-entity", "n4-chunk", "EXTRACTED_FROM"),
  graphEdge("g-person-email", "n4-person", "n4-email", "SENT / SENT_TO"),
];
