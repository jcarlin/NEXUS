"""Curated queryable schema for Text-to-SQL generation.

Defines which tables are safe for natural language querying and provides
accurate column descriptions from the database schema. Security-sensitive
tables (users, audit_log, ai_audit_log, auth tables) are excluded.

The schema description string is used as LLM context so the model generates
valid SQL against the actual table structure.
"""

from __future__ import annotations

# Tables that are safe to query via Text-to-SQL
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "documents",
        "annotations",
        "memos",
        "chat_messages",
        "jobs",
        "datasets",
        "dataset_documents",
        "document_tags",
        "case_matters",
        "case_contexts",
        "case_claims",
        "case_parties",
        "case_defined_terms",
        "communication_pairs",
        "production_sets",
        "production_set_documents",
        "export_jobs",
        "evaluation_dataset_items",
        "evaluation_runs",
        "redactions",
        "edrm_import_log",
        "bulk_import_jobs",
    }
)

# Tables that must NEVER be queried (security / auth / audit)
FORBIDDEN_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "audit_log",
        "ai_audit_log",
        "agent_audit_log",
        "feature_flag_overrides",
        "llm_providers",
        "llm_tier_config",
        "user_case_matters",
        "google_drive_connections",
        "google_drive_sync_state",
        "retention_policies",
        "dataset_access",
    }
)

# Schema description for LLM context — accurate column definitions from
# migrations and docs/database-schema.md
QUERYABLE_SCHEMA_DESCRIPTION: str = """\
Safe queryable tables (PostgreSQL):

1. documents (ingested document metadata):
   - id (UUID PK), job_id (UUID FK), matter_id (UUID FK), filename (VARCHAR),
     document_type (VARCHAR), page_count (INT), chunk_count (INT),
     entity_count (INT), minio_path (VARCHAR), file_size_bytes (BIGINT),
     content_hash (VARCHAR), metadata_ (JSONB),
     created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ),
     privilege_status (VARCHAR), message_id (VARCHAR), in_reply_to (VARCHAR),
     thread_id (VARCHAR), thread_position (INT), is_inclusive (BOOLEAN),
     duplicate_cluster_id (VARCHAR), duplicate_score (FLOAT),
     version_group_id (VARCHAR), version_number (INT), is_final_version (BOOLEAN),
     import_source (VARCHAR),
     sentiment_positive (FLOAT), sentiment_negative (FLOAT),
     sentiment_pressure (FLOAT), sentiment_opportunity (FLOAT),
     sentiment_rationalization (FLOAT), sentiment_intent (FLOAT),
     sentiment_concealment (FLOAT),
     hot_doc_score (FLOAT), context_gap_score (FLOAT), anomaly_score (FLOAT),
     bates_begin (VARCHAR), bates_end (VARCHAR), redacted_pdf_path (VARCHAR)

2. annotations (user annotations on documents):
   - id (UUID PK), document_id (UUID FK), matter_id (UUID),
     user_id (UUID), page_number (INT), annotation_type (VARCHAR),
     content (TEXT), anchor (JSONB), color (VARCHAR),
     created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ)

3. memos (persisted legal memos):
   - id (UUID PK), matter_id (UUID FK), thread_id (VARCHAR),
     title (VARCHAR), sections (JSONB), format (VARCHAR),
     created_by (UUID FK), created_at (TIMESTAMPTZ)

4. chat_messages (conversation history):
   - id (UUID PK), thread_id (UUID), matter_id (UUID FK),
     role (VARCHAR), content (TEXT), source_documents (JSONB),
     entities_mentioned (JSONB), follow_up_questions (JSONB),
     metadata_ (JSONB), created_at (TIMESTAMPTZ)

5. jobs (ingestion pipeline jobs):
   - id (UUID PK), filename (VARCHAR), status (VARCHAR), stage (VARCHAR),
     progress (JSONB), error (TEXT), parent_job_id (UUID FK),
     matter_id (UUID FK), dataset_id (UUID FK), metadata_ (JSONB),
     created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ)

6. datasets (document collections/folders):
   - id (UUID PK), matter_id (UUID FK), name (VARCHAR),
     description (TEXT), parent_id (UUID FK self-ref),
     created_by (UUID FK), created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ)

7. dataset_documents (document-to-dataset assignments):
   - dataset_id (UUID PK composite FK), document_id (UUID PK composite FK),
     assigned_at (TIMESTAMPTZ), assigned_by (UUID FK)

8. document_tags (labels on documents):
   - document_id (UUID PK composite FK), tag_name (VARCHAR PK composite),
     created_at (TIMESTAMPTZ), created_by (UUID FK)

9. case_matters (top-level organizational units):
   - id (UUID PK), name (VARCHAR), description (TEXT),
     is_active (BOOLEAN), created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ)

10. case_contexts (extracted case context per matter):
    - id (UUID PK), matter_id (UUID), anchor_document_id (VARCHAR),
      status (VARCHAR), timeline (JSON),
      created_at (TIMESTAMPTZ), updated_at (TIMESTAMPTZ)

11. case_claims (legal claims from case context):
    - id (UUID PK), case_context_id (UUID FK), claim_number (INT),
      claim_label (VARCHAR), claim_text (TEXT), legal_elements (JSON),
      source_pages (JSON), created_at (TIMESTAMPTZ)

12. case_parties (parties involved in the case):
    - id (UUID PK), case_context_id (UUID FK), name (VARCHAR),
      role (VARCHAR), description (TEXT), aliases (JSON),
      entity_id (VARCHAR), source_pages (JSON), created_at (TIMESTAMPTZ)

13. case_defined_terms (legal terms with definitions):
    - id (UUID PK), case_context_id (UUID FK), term (VARCHAR),
      definition (TEXT), entity_id (VARCHAR), source_pages (JSON),
      created_at (TIMESTAMPTZ)

14. communication_pairs (sender-recipient email pairs):
    - id (UUID PK), matter_id (UUID), sender_name (VARCHAR),
      sender_email (VARCHAR), recipient_name (VARCHAR),
      recipient_email (VARCHAR), relationship_type (VARCHAR),
      message_count (INT), earliest (TIMESTAMPTZ), latest (TIMESTAMPTZ)

15. production_sets (document sets for legal production):
    - id (UUID PK), matter_id (UUID), name (VARCHAR),
      description (TEXT), bates_prefix (VARCHAR), status (VARCHAR),
      created_at (TIMESTAMPTZ)

16. evaluation_dataset_items (ground-truth Q&A pairs):
    - id (UUID PK), dataset_type (VARCHAR), question (TEXT),
      expected_answer (TEXT), tags (JSON), created_at (TIMESTAMPTZ)

17. evaluation_runs (evaluation pipeline results):
    - id (UUID PK), mode (VARCHAR), status (VARCHAR),
      metrics (JSON), total_items (INT), processed_items (INT),
      created_at (TIMESTAMPTZ), completed_at (TIMESTAMPTZ)

IMPORTANT: All queries MUST include WHERE matter_id = :matter_id.
Tables without matter_id (evaluation_dataset_items, evaluation_runs) can
be queried without this filter.

Never query: users, audit_log, ai_audit_log, agent_audit_log, sessions,
feature_flag_overrides, llm_providers, llm_tier_config, user_case_matters,
google_drive_connections, google_drive_sync_state, retention_policies,
dataset_access, or any auth tables."""
