export type Role = "admin" | "attorney" | "paralegal" | "reviewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Matter {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface SourceDocument {
  id: string;
  filename: string;
  page?: number | null;
  chunk_text: string;
  relevance_score: number;
  preview_url?: string | null;
  download_url?: string | null;
}

export interface EntityMention {
  name: string;
  type: string;
  kg_id?: string | null;
  connections: number;
}

export interface CitedClaim {
  claim_text: string;
  document_id: string;
  filename: string;
  page_number?: number | null;
  bates_range?: string | null;
  excerpt: string;
  grounding_score: number;
  verification_status: "unverified" | "verified" | "flagged";
}

export interface QueryResponse {
  response: string;
  source_documents: SourceDocument[];
  follow_up_questions: string[];
  entities_mentioned: EntityMention[];
  thread_id: string;
  message_id: string;
  cited_claims: CitedClaim[];
  tier?: string | null;
}

export interface ChatThread {
  thread_id: string;
  message_count: number;
  last_message_at: string;
  first_query: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  source_documents: SourceDocument[];
  entities_mentioned: EntityMention[];
  follow_up_questions: string[];
  timestamp: string;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  type?: string | null;
  page_count: number;
  chunk_count: number;
  entity_count: number;
  created_at: string;
  minio_path: string;
  privilege_status?: string | null;
  thread_id?: string | null;
  is_inclusive?: boolean | null;
  duplicate_cluster_id?: string | null;
  version_group_id?: string | null;
}

export interface DocumentDetail extends DocumentResponse {
  metadata_: Record<string, unknown>;
  file_size_bytes?: number | null;
  content_hash?: string | null;
  job_id?: string | null;
  updated_at?: string | null;
  privilege_reviewed_by?: string | null;
  privilege_reviewed_at?: string | null;
  message_id?: string | null;
  in_reply_to?: string | null;
  thread_position?: number | null;
  duplicate_score?: number | null;
  version_number?: number | null;
  is_final_version?: boolean | null;
  sentiment_positive?: number | null;
  sentiment_negative?: number | null;
  sentiment_pressure?: number | null;
  sentiment_opportunity?: number | null;
  sentiment_rationalization?: number | null;
  sentiment_intent?: number | null;
  sentiment_concealment?: number | null;
  hot_doc_score?: number | null;
  context_gap_score?: number | null;
  context_gaps?: string[] | null;
  anomaly_score?: number | null;
  bates_begin?: string | null;
  bates_end?: string | null;
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
  node_count: number;
  edge_count: number;
  entity_types: Record<string, number>;
}

export interface TimelineEvent {
  date?: string | null;
  description: string;
  entities: string[];
  document_source?: string | null;
}

export interface AuditLogEntry {
  id: string;
  user_id?: string | null;
  user_email?: string | null;
  action: string;
  resource: string;
  resource_type?: string | null;
  matter_id?: string | null;
  ip_address: string;
  user_agent?: string | null;
  status_code: number;
  duration_ms?: number | null;
  request_id?: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  filename?: string | null;
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
}

export type SSEEvent =
  | { type: "status"; stage: string }
  | { type: "sources"; documents: SourceDocument[] }
  | { type: "token"; text: string }
  | {
      type: "done";
      thread_id: string;
      follow_ups: string[];
      entities: EntityMention[];
      cited_claims: CitedClaim[];
      tier?: string | null;
    };

export interface DatasetResponse {
  id: string;
  matter_id: string;
  name: string;
  description: string;
  parent_id: string | null;
  document_count: number;
  children_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

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

export interface TagResponse {
  tag_name: string;
  document_count: number;
}

// --- Dataset Access Control ---

export type DatasetAccessRole = "viewer" | "editor" | "admin";

export interface DatasetAccessResponse {
  id: string;
  dataset_id: string;
  user_id: string;
  access_role: DatasetAccessRole;
  granted_by: string | null;
  granted_at: string;
}

// --- Annotations ---

export type AnnotationType = "note" | "highlight" | "tag";

export interface AnnotationAnchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

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
