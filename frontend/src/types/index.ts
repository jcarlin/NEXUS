// ---------------------------------------------------------------------------
// Re-exports from orval-generated schemas (single source of truth)
// ---------------------------------------------------------------------------
// Alias where the generated name differs from established usage.
// Import first so client-only types below can reference them.

import type {
  EntityMention as _EntityMention,
  CitedClaim as _CitedClaim,
} from "@/api/generated/schemas";

export type { Role } from "@/api/generated/schemas";
export type { UserResponse as User } from "@/api/generated/schemas";
export type { TokenResponse } from "@/api/generated/schemas";
export type { MatterResponse as Matter } from "@/api/generated/schemas";
export type { EntityMention } from "@/api/generated/schemas";
export type { CitedClaim } from "@/api/generated/schemas";
export type { DocumentResponse } from "@/api/generated/schemas";
export type { DocumentDetail } from "@/api/generated/schemas";
export type { AuditLogEntry } from "@/api/generated/schemas";
// NOTE: Generated JobStatusResponse uses JobStatus enum (not string) and has
// different field optionality. Keep local type.
export type { DatasetResponse } from "@/api/generated/schemas";
// NOTE: Generated DatasetTreeNode has optional `children` and `document_count`
// but consumers assume these are always present. Keep local types.
export type { TagResponse } from "@/api/generated/schemas";
export type { DatasetAccessRole } from "@/api/generated/schemas";
export type { DatasetAccessResponse } from "@/api/generated/schemas";
// NOTE: Generated AnnotationType is a const enum pattern, not compatible with
// string union usage (e.g. `Record<AnnotationType, ...>` indexing). Keep local.
// NOTE: Generated AnnotationResponse/Create/Update use incompatible anchor and
// annotation_type types (orval nullable wrappers vs local AnnotationAnchor).
// Keep local types.
export type { DatasetIngestRequest } from "@/api/generated/schemas";
export type { DatasetIngestResponse } from "@/api/generated/schemas";
export type { DryRunEstimate } from "@/api/generated/schemas";
// NOTE: The generated AppIngestionSchemasBulkImportStatusResponse uses
// `import_id` instead of `id` and lacks `source_path`, `completed_at`.
// Keep the local type until the backend OpenAPI spec is reconciled.
export type { ThreadResponse } from "@/api/generated/schemas";
export type { CommunicationMatrixResponse } from "@/api/generated/schemas";
export type { CommunicationPair } from "@/api/generated/schemas";
export type { ProductionSetResponse } from "@/api/generated/schemas";
export type { ExportJobResponse } from "@/api/generated/schemas";
export type { DuplicateCluster } from "@/api/generated/schemas";
export type { EvalRunResponse } from "@/api/generated/schemas";
export type { EDRMImportResponse } from "@/api/generated/schemas";
export type { PIIDetection } from "@/api/generated/schemas";
export type { RedactionLogEntry } from "@/api/generated/schemas";
export type { RedactionLogResponse } from "@/api/generated/schemas";
export type { ProductionSetDocumentResponse } from "@/api/generated/schemas";
export type { DatasetItemResponse } from "@/api/generated/schemas";
export type { ClaimResponse } from "@/api/generated/schemas";
export type { PartyResponse } from "@/api/generated/schemas";
export type { PartyRole } from "@/api/generated/schemas";
export type { DefinedTermResponse } from "@/api/generated/schemas";
export type { LatestEvalResponse } from "@/api/generated/schemas";
export type { CaseContextResponse } from "@/api/generated/schemas";
export type { ProcessUploadedRequest } from "@/api/generated/schemas";
export type { ProcessUploadedFile } from "@/api/generated/schemas";

// ---------------------------------------------------------------------------
// Memo types
// ---------------------------------------------------------------------------

export interface MemoSection {
  heading: string;
  content: string;
  citations: string[];
}

export interface MemoResponse {
  id: string;
  matter_id: string;
  thread_id: string | null;
  title: string;
  sections: MemoSection[];
  format: "markdown" | "html";
  created_by: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Client-only types (no generated equivalent)
// ---------------------------------------------------------------------------

/**
 * Source document with optional doc_id for citation sidebar downloads.
 * NOTE: The generated SourceDocument schema is missing `doc_id` — this is a
 * backend OpenAPI spec gap (the field is returned at runtime). Keep this
 * extended version until the spec is fixed.
 */
export interface SourceDocument {
  id: string;
  doc_id?: string | null;
  filename: string;
  page?: number | null;
  chunk_text: string;
  relevance_score: number;
  preview_url?: string | null;
  download_url?: string | null;
}

export interface EntityResponse {
  id: string;
  name: string;
  type: string;
  aliases: string[];
  first_seen?: string | null;
  last_seen?: string | null;
  description?: string | null;
  mention_count: number;
}

export interface EntityConnection {
  source: string;
  target: string;
  relationship_type: string;
  context?: string | null;
  weight: number;
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  node_counts: Record<string, number>;
}

export interface TimelineEvent {
  date?: string | null;
  description: string;
  entities: string[];
  document_source?: string | null;
}

export interface ChatThread {
  thread_id: string;
  message_count: number;
  last_message_at: string;
  first_query: string;
}

export interface ToolCallEntry {
  tool: string;
  label: string;
  kind?: "tool" | "step";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  source_documents: SourceDocument[];
  entities_mentioned: _EntityMention[];
  follow_up_questions: string[];
  cited_claims: _CitedClaim[];
  tool_calls?: ToolCallEntry[];
  timestamp: string;
}

export interface QueryResponse {
  response: string;
  source_documents: SourceDocument[];
  follow_up_questions: string[];
  entities_mentioned: _EntityMention[];
  thread_id: string;
  message_id: string;
  cited_claims: _CitedClaim[];
  tier?: string | null;
}

export type SSEEvent =
  | { type: "status"; stage: string }
  | { type: "sources"; documents: SourceDocument[] }
  | { type: "token"; text: string }
  | { type: "interrupt"; question: string; thread_id: string }
  | {
      type: "done";
      thread_id: string;
      follow_ups: string[];
      entities: _EntityMention[];
      cited_claims: _CitedClaim[];
      tier?: string | null;
    };

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export type AnnotationType = "note" | "highlight" | "tag";

export interface Annotation {
  id: string;
  document_id: string;
  matter_id: string;
  user_id: string;
  page_number: number | null;
  annotation_type: AnnotationType;
  content: string;
  anchor: AnnotationAnchor | Record<string, never>;
  color: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnnotationCreate {
  document_id: string;
  page_number?: number | null;
  annotation_type?: AnnotationType;
  content: string;
  anchor?: AnnotationAnchor;
  color?: string | null;
}

export interface AnnotationUpdate {
  content?: string | null;
  anchor?: AnnotationAnchor | null;
  color?: string | null;
}

export interface AnnotationAnchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type AdapterType =
  | "directory"
  | "huggingface_csv"
  | "edrm_xml"
  | "concordance_dat";

export interface DatasetTreeNode {
  id: string;
  name: string;
  description: string;
  document_count: number;
  children: DatasetTreeNode[];
}

export interface DatasetTreeResponse {
  roots: DatasetTreeNode[];
  total_datasets: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  filename?: string | null;
  label?: string | null;
  task_type?: string | null;
  document_type?: string | null;
  error?: string | null;
  progress?: {
    stage: string;
    pages_parsed: number;
    chunks_created: number;
    entities_extracted: number;
    embeddings_generated: number;
  } | null;
  created_at: string;
  updated_at?: string | null;
  completed_at?: string | null;
  file_size_bytes?: number | null;
  page_count?: number | null;
}

export interface BulkImportStatusResponse {
  id: string;
  status: string;
  adapter_type: string;
  source_path: string;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
  skipped_documents: number;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  total_size_bytes?: number;
  total_pages?: number;
}
