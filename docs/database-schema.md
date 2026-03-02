# Database Schema Reference

PostgreSQL 16. All schema changes via Alembic migrations. Raw SQL via `sqlalchemy.text()` (no ORM).

Connection string pattern (from `alembic.ini`, overridden at runtime by `app.config.Settings`):

```
postgresql://nexus:changeme@localhost:5432/nexus
```

## Migration Index

| # | Revision | Description |
|---|----------|-------------|
| 001 | `001` | Initial schema -- jobs, documents, chat_messages |
| 002 | `002` | Auth tables (users, case_matters, user_case_matters) and matter_id FK on existing tables |
| 003 | `003` | Audit log table and privilege columns on documents |
| 004 | `004` | SOC 2 audit readiness -- ai_audit_log, agent_audit_log, session tracking, immutability rules |
| 005 | `005` | EDRM interop -- email threading, near-duplicate detection, version tracking on documents; edrm_import_log table |
| 006 | `006` | Case intelligence -- case_contexts, case_claims, case_parties, case_defined_terms, investigation_sessions |
| 007 | `007` | Bulk import -- import_source column on documents, content_hash index, bulk_import_jobs table |
| 008 | `008` | Communication analytics -- communication_pairs and org_chart_entries tables |
| 009 | `009` | Sentiment analysis and hot doc detection columns on documents |
| 010 | `010` | Annotations, production sets, production_set_documents, export_jobs; bates columns on documents |
| 011 | `011` | Redactions table and redacted_pdf_path column on documents |
| 012 | `012` | Evaluation pipeline -- evaluation_dataset_items and evaluation_runs tables |
| 013 | `013` | Dataset/collection management -- datasets, dataset_documents, document_tags, dataset_access; dataset_id on jobs |

---

## Tables by Domain

### Core

#### `jobs`

Tracks ingestion pipeline runs.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| filename | VARCHAR | NOT NULL | Original upload filename |
| status | VARCHAR | NOT NULL, DEFAULT `'pending'` | Job lifecycle status |
| stage | VARCHAR | DEFAULT `'uploading'` | Current pipeline stage |
| progress | JSONB | DEFAULT `'{}'` | Stage-by-stage progress details |
| error | TEXT | NULLABLE | Error message on failure |
| parent_job_id | UUID | FK -> jobs.id, NULLABLE | For sub-jobs (e.g., ZIP extraction) |
| matter_id | UUID | FK -> case_matters.id, NULLABLE | Added in 002 |
| dataset_id | UUID | FK -> datasets.id ON DELETE SET NULL, NULLABLE | Target dataset for ingestion; added in 013 |
| metadata_ | JSONB | DEFAULT `'{}'` | Arbitrary metadata |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

**Indexes:**
- `idx_jobs_matter_id` on (`matter_id`)

---

#### `documents`

Ingested document metadata. Heavily extended across migrations 003, 005, 007, 009, 010, 011.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| job_id | UUID | FK -> jobs.id, NULLABLE | Originating ingestion job |
| matter_id | UUID | FK -> case_matters.id, NULLABLE | All queries scoped by matter; added in 002 |
| filename | VARCHAR | NOT NULL | Original filename |
| document_type | VARCHAR | NULLABLE | File type (pdf, docx, eml, etc.) |
| page_count | INTEGER | DEFAULT 0 | |
| chunk_count | INTEGER | DEFAULT 0 | |
| entity_count | INTEGER | DEFAULT 0 | |
| minio_path | VARCHAR | NOT NULL | Object storage path |
| file_size_bytes | BIGINT | NULLABLE | |
| content_hash | VARCHAR | NULLABLE | SHA-256 of file content; indexed in 007 |
| metadata_ | JSONB | DEFAULT `'{}'` | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |
| **Privilege (003)** | | | |
| privilege_status | VARCHAR(50) | NULLABLE | e.g., `privileged`, `not_privileged`, `needs_review` |
| privilege_reviewed_by | UUID | FK -> users.id ON DELETE SET NULL, NULLABLE | |
| privilege_reviewed_at | TIMESTAMPTZ | NULLABLE | |
| **Email Threading (005)** | | | |
| message_id | VARCHAR(512) | NULLABLE | RFC 2822 Message-ID |
| in_reply_to | VARCHAR(512) | NULLABLE | RFC 2822 In-Reply-To |
| references_ | TEXT | NULLABLE | RFC 2822 References header |
| thread_id | VARCHAR(128) | NULLABLE | Computed thread cluster ID |
| thread_position | INTEGER | NULLABLE | Position within thread |
| is_inclusive | BOOLEAN | NULLABLE | Whether this is the inclusive (latest) email in thread |
| **Near-Duplicate Detection (005)** | | | |
| duplicate_cluster_id | VARCHAR(128) | NULLABLE | Cluster ID for near-dupes |
| duplicate_score | FLOAT | NULLABLE | Similarity score within cluster |
| **Version Tracking (005)** | | | |
| version_group_id | VARCHAR(128) | NULLABLE | Groups document versions together |
| version_number | INTEGER | NULLABLE | Version sequence number |
| is_final_version | BOOLEAN | NULLABLE | |
| **Bulk Import (007)** | | | |
| import_source | VARCHAR(128) | NULLABLE | e.g., `bulk_import`, `webhook`, `api` |
| **Sentiment & Hot Docs (009)** | | | |
| sentiment_positive | FLOAT | NULLABLE | |
| sentiment_negative | FLOAT | NULLABLE | |
| sentiment_pressure | FLOAT | NULLABLE | Fraud triangle: pressure indicator |
| sentiment_opportunity | FLOAT | NULLABLE | Fraud triangle: opportunity indicator |
| sentiment_rationalization | FLOAT | NULLABLE | Fraud triangle: rationalization indicator |
| sentiment_intent | FLOAT | NULLABLE | |
| sentiment_concealment | FLOAT | NULLABLE | |
| hot_doc_score | FLOAT | NULLABLE | Composite hot-document score |
| context_gap_score | FLOAT | NULLABLE | Measures missing context |
| context_gaps | JSONB | NULLABLE | Structured gap details |
| anomaly_score | FLOAT | NULLABLE | Statistical anomaly score |
| **Bates Numbering (010)** | | | |
| bates_begin | VARCHAR(100) | NULLABLE | First Bates number assigned |
| bates_end | VARCHAR(100) | NULLABLE | Last Bates number assigned |
| **Redaction (011)** | | | |
| redacted_pdf_path | VARCHAR(500) | NULLABLE | MinIO path to redacted PDF |

**Indexes:**
- `idx_documents_matter_id` on (`matter_id`)
- `idx_documents_content_hash` on (`content_hash`)
- `ix_documents_privilege_status` on (`privilege_status`)
- `ix_documents_thread_id` on (`thread_id`)
- `ix_documents_message_id` on (`message_id`)
- `ix_documents_duplicate_cluster_id` on (`duplicate_cluster_id`)
- `ix_documents_version_group_id` on (`version_group_id`)
- `ix_documents_hot_doc_score` on (`hot_doc_score`)
- `ix_documents_context_gap_score` on (`context_gap_score`)
- `ix_documents_anomaly_score` on (`anomaly_score`)
- `ix_documents_bates_begin` on (`bates_begin`)

---

#### `chat_messages`

Conversation history for the query domain.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| thread_id | UUID | NOT NULL | Groups messages into conversations |
| matter_id | UUID | FK -> case_matters.id, NULLABLE | Added in 002 |
| role | VARCHAR | NOT NULL | `user`, `assistant`, `system` |
| content | TEXT | NOT NULL | Message body |
| source_documents | JSONB | DEFAULT `'[]'` | Referenced document IDs + metadata |
| entities_mentioned | JSONB | DEFAULT `'[]'` | Entity IDs surfaced in response |
| follow_up_questions | JSONB | DEFAULT `'[]'` | Suggested follow-ups |
| metadata_ | JSONB | DEFAULT `'{}'` | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |

**Indexes:**
- `idx_chat_messages_thread` on (`thread_id`, `created_at`)
- `idx_chat_messages_matter_id` on (`matter_id`)

---

### Auth

#### `users`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| email | VARCHAR(255) | NOT NULL, UNIQUE | |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hash |
| full_name | VARCHAR(255) | NOT NULL | |
| role | VARCHAR(50) | NOT NULL, DEFAULT `'reviewer'` | One of: `admin`, `attorney`, `reviewer`, `viewer` |
| api_key_hash | VARCHAR(255) | NULLABLE | Hashed API key for programmatic access |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | Soft-disable account |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

**Indexes:**
- `idx_users_email` on (`email`) UNIQUE

**Seed data:** Admin user (`admin@nexus.dev`, role `admin`) inserted by migration 002.

---

#### `case_matters`

Top-level organizational unit. All data is scoped by matter.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| name | VARCHAR(255) | NOT NULL | |
| description | TEXT | NULLABLE | |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

**Seed data:** Default matter inserted by migration 002.

---

#### `user_case_matters`

Join table: assigns users to matters.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| user_id | UUID | PK (composite), FK -> users.id ON DELETE CASCADE | |
| matter_id | UUID | PK (composite), FK -> case_matters.id ON DELETE CASCADE | |
| assigned_at | TIMESTAMPTZ | DEFAULT now() | |

---

### Audit

#### `audit_log`

Append-only API request audit trail. Protected by PostgreSQL RULEs against UPDATE and DELETE (added in 004).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| user_id | UUID | FK -> users.id ON DELETE SET NULL, NULLABLE | |
| user_email | VARCHAR(255) | NULLABLE | Denormalized for fast querying |
| action | VARCHAR(50) | NOT NULL | HTTP method or action name |
| resource | VARCHAR(500) | NOT NULL | Request path |
| resource_type | VARCHAR(100) | NULLABLE | e.g., `document`, `query`, `entity` |
| matter_id | UUID | NULLABLE | |
| ip_address | VARCHAR(45) | NOT NULL | Supports IPv6 |
| user_agent | TEXT | NULLABLE | |
| status_code | INTEGER | NOT NULL | HTTP response status |
| duration_ms | FLOAT | NULLABLE | Request duration |
| request_id | VARCHAR(64) | NULLABLE | Correlation ID |
| session_id | UUID | NULLABLE | Session tracking; added in 004 |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_audit_log_created_at` on (`created_at DESC`)
- `ix_audit_log_user_id` on (`user_id`)
- `ix_audit_log_matter_id` on (`matter_id`)
- `ix_audit_log_resource_type` on (`resource_type`)
- `ix_audit_log_session_id` on (`session_id`)

**Immutability rules (004):**
- `audit_log_no_update` -- RULE: ON UPDATE DO INSTEAD NOTHING
- `audit_log_no_delete` -- RULE: ON DELETE DO INSTEAD NOTHING

---

#### `ai_audit_log`

Tracks every LLM/AI API call for SOC 2 compliance. Append-only.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| request_id | VARCHAR(64) | NULLABLE | Correlation ID |
| session_id | UUID | NULLABLE | |
| user_id | UUID | FK -> users.id ON DELETE SET NULL, NULLABLE | |
| matter_id | UUID | NULLABLE | |
| call_type | VARCHAR(50) | NOT NULL, DEFAULT `'completion'` | e.g., `completion`, `embedding`, `extraction` |
| node_name | VARCHAR(100) | NULLABLE | LangGraph node that made the call |
| provider | VARCHAR(50) | NOT NULL | `anthropic`, `openai`, `vllm` |
| model | VARCHAR(100) | NOT NULL | Model identifier |
| prompt_hash | VARCHAR(64) | NULLABLE | SHA-256 of prompt template (no content) |
| input_tokens | INTEGER | NULLABLE | |
| output_tokens | INTEGER | NULLABLE | |
| total_tokens | INTEGER | NULLABLE | |
| latency_ms | FLOAT | NULLABLE | |
| status | VARCHAR(20) | NOT NULL, DEFAULT `'success'` | |
| error_message | TEXT | NULLABLE | |
| metadata_ | JSON | NOT NULL, DEFAULT `'{}'::jsonb` | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_ai_audit_log_created_at` on (`created_at DESC`)
- `ix_ai_audit_log_session_id` on (`session_id`)
- `ix_ai_audit_log_user_id` on (`user_id`)
- `ix_ai_audit_log_request_id` on (`request_id`)
- `ix_ai_audit_log_matter_id` on (`matter_id`)

**Immutability rules (004):**
- `ai_audit_log_no_update` -- RULE: ON UPDATE DO INSTEAD NOTHING
- `ai_audit_log_no_delete` -- RULE: ON DELETE DO INSTEAD NOTHING

---

#### `agent_audit_log`

Tracks agentic actions (tool use, iteration steps). Append-only. Schema created in 004; populated by future agent milestones.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| session_id | UUID | NULLABLE | |
| agent_id | VARCHAR(100) | NOT NULL | Agent identifier |
| request_id | VARCHAR(64) | NULLABLE | |
| user_id | UUID | FK -> users.id ON DELETE SET NULL, NULLABLE | |
| matter_id | UUID | NULLABLE | |
| action_type | VARCHAR(100) | NOT NULL | e.g., `tool_call`, `plan`, `assess` |
| action_name | VARCHAR(200) | NULLABLE | Specific tool or step name |
| input_summary | TEXT | NULLABLE | Sanitized summary (no document content) |
| output_summary | TEXT | NULLABLE | Sanitized summary |
| iteration_number | INTEGER | NULLABLE | Loop iteration index |
| duration_ms | FLOAT | NULLABLE | |
| status | VARCHAR(20) | NOT NULL, DEFAULT `'success'` | |
| metadata_ | JSON | NOT NULL, DEFAULT `'{}'::jsonb` | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_agent_audit_log_created_at` on (`created_at DESC`)
- `ix_agent_audit_log_session_id` on (`session_id`)
- `ix_agent_audit_log_agent_id` on (`agent_id`)

**Immutability rules (004):**
- `agent_audit_log_no_update` -- RULE: ON UPDATE DO INSTEAD NOTHING
- `agent_audit_log_no_delete` -- RULE: ON DELETE DO INSTEAD NOTHING

---

### EDRM

#### `edrm_import_log`

Tracks EDRM load-file imports.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| filename | VARCHAR(500) | NOT NULL | Load file name |
| format | VARCHAR(50) | NOT NULL | e.g., `dat`, `opt`, `csv` |
| record_count | INTEGER | NOT NULL, DEFAULT 0 | |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'pending'` | |
| error | TEXT | NULLABLE | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| completed_at | TIMESTAMPTZ | NULLABLE | |

**Indexes:**
- `ix_edrm_import_log_matter_id` on (`matter_id`)

---

### Cases

#### `case_contexts`

Stores extracted case context (claims, parties, timeline) per matter. One active context per matter.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| anchor_document_id | VARCHAR(256) | NOT NULL | Document used as source for extraction |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'processing'` | `processing`, `ready`, `confirmed` |
| created_by | UUID | NULLABLE | User who triggered extraction |
| confirmed_by | UUID | NULLABLE | User who confirmed the context |
| confirmed_at | TIMESTAMPTZ | NULLABLE | |
| job_id | VARCHAR(256) | NULLABLE | Background job ID |
| timeline | JSON | NULLABLE | Extracted timeline events |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_case_contexts_matter_id` on (`matter_id`) UNIQUE

---

#### `case_claims`

Legal claims extracted from case context documents.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| case_context_id | UUID | FK -> case_contexts.id ON DELETE CASCADE, NOT NULL | |
| claim_number | INTEGER | NOT NULL | Ordered claim index |
| claim_label | VARCHAR(500) | NOT NULL | Short label |
| claim_text | TEXT | NOT NULL | Full claim text |
| legal_elements | JSON | NULLABLE | Structured elements of the claim |
| source_pages | JSON | NULLABLE | Page references |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_case_claims_context_id` on (`case_context_id`)

---

#### `case_parties`

Parties involved in the case (plaintiffs, defendants, counsel, etc.).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| case_context_id | UUID | FK -> case_contexts.id ON DELETE CASCADE, NOT NULL | |
| name | VARCHAR(500) | NOT NULL | Party name |
| role | VARCHAR(50) | NOT NULL | e.g., `plaintiff`, `defendant`, `witness` |
| description | TEXT | NULLABLE | |
| aliases | JSON | NULLABLE | Alternative names / spellings |
| entity_id | VARCHAR(256) | NULLABLE | Link to knowledge graph entity |
| source_pages | JSON | NULLABLE | Page references |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_case_parties_context_id` on (`case_context_id`)

---

#### `case_defined_terms`

Legal terms with definitions extracted from case documents.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| case_context_id | UUID | FK -> case_contexts.id ON DELETE CASCADE, NOT NULL | |
| term | VARCHAR(500) | NOT NULL | The defined term |
| definition | TEXT | NOT NULL | Its definition |
| entity_id | VARCHAR(256) | NULLABLE | Link to knowledge graph entity |
| source_pages | JSON | NULLABLE | Page references |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_case_defined_terms_context_id` on (`case_context_id`)

---

#### `investigation_sessions`

User investigation sessions with saved findings.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| case_context_id | UUID | FK -> case_contexts.id ON DELETE SET NULL, NULLABLE | |
| user_id | UUID | NOT NULL | |
| title | VARCHAR(500) | NULLABLE | |
| findings | JSON | NULLABLE | Saved investigation findings |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'active'` | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_investigation_sessions_matter_id` on (`matter_id`)

---

### Bulk Import

#### `bulk_import_jobs`

Tracks bulk import operations (e.g., pre-OCR'd dataset ingestion).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| adapter_type | VARCHAR(64) | NULLABLE | e.g., `csv_adapter`, `edrm_adapter` |
| source_path | VARCHAR(1024) | NULLABLE | Path to source data |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'pending'` | |
| total_documents | INTEGER | NULLABLE | |
| processed_documents | INTEGER | NOT NULL, DEFAULT 0 | |
| failed_documents | INTEGER | NOT NULL, DEFAULT 0 | |
| skipped_documents | INTEGER | NOT NULL, DEFAULT 0 | |
| error | TEXT | NULLABLE | |
| metadata_ | JSON | NULLABLE | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| completed_at | TIMESTAMPTZ | NULLABLE | |

**Indexes:**
- `ix_bulk_import_jobs_matter_id` on (`matter_id`)

---

### Analytics

#### `communication_pairs`

Aggregated sender-recipient communication pairs extracted from email metadata.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| sender_name | VARCHAR(500) | NOT NULL | |
| sender_email | VARCHAR(500) | NULLABLE | |
| recipient_name | VARCHAR(500) | NOT NULL | |
| recipient_email | VARCHAR(500) | NULLABLE | |
| relationship_type | VARCHAR(10) | NOT NULL, DEFAULT `'to'` | `to`, `cc`, `bcc` |
| message_count | INTEGER | NOT NULL, DEFAULT 0 | |
| earliest | TIMESTAMPTZ | NULLABLE | Earliest message in pair |
| latest | TIMESTAMPTZ | NULLABLE | Latest message in pair |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_comm_pairs_matter` on (`matter_id`)

**Unique constraint:** `uq_comm_pairs_sender_recipient_type` on (`matter_id`, `sender_email`, `recipient_email`, `relationship_type`)

---

#### `org_chart_entries`

Inferred or manually entered organizational hierarchy.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| person_name | VARCHAR(500) | NOT NULL | |
| person_email | VARCHAR(500) | NULLABLE | |
| reports_to_name | VARCHAR(500) | NULLABLE | |
| reports_to_email | VARCHAR(500) | NULLABLE | |
| title | VARCHAR(500) | NULLABLE | Job title |
| department | VARCHAR(500) | NULLABLE | |
| source | VARCHAR(50) | NOT NULL, DEFAULT `'manual'` | `manual`, `inferred`, `imported` |
| confidence | FLOAT | NULLABLE | For inferred entries |
| confirmed_by | UUID | NULLABLE | |
| confirmed_at | TIMESTAMPTZ | NULLABLE | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_org_chart_matter` on (`matter_id`)

---

### Annotations & Exports

#### `annotations`

User annotations on documents (notes, highlights, tags).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| document_id | UUID | FK -> documents.id ON DELETE CASCADE, NOT NULL | |
| matter_id | UUID | NOT NULL | |
| user_id | UUID | NOT NULL | |
| page_number | INTEGER | NULLABLE | |
| annotation_type | VARCHAR(50) | NOT NULL, DEFAULT `'note'` | e.g., `note`, `highlight`, `tag`, `issue` |
| content | TEXT | NOT NULL | Annotation body |
| anchor | JSONB | NOT NULL, DEFAULT `'{}'::jsonb` | Position/selection anchor data |
| color | VARCHAR(20) | NULLABLE | Display color |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_annotations_matter_id` on (`matter_id`)
- `ix_annotations_document_id` on (`document_id`)
- `ix_annotations_user_id` on (`user_id`)

---

#### `production_sets`

Named sets of documents prepared for legal production.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| name | VARCHAR(255) | NOT NULL | |
| description | TEXT | NULLABLE | |
| bates_prefix | VARCHAR(50) | NOT NULL, DEFAULT `'NEXUS'` | Prefix for Bates numbering |
| bates_start | INTEGER | NOT NULL, DEFAULT 1 | Starting Bates number |
| bates_padding | INTEGER | NOT NULL, DEFAULT 6 | Zero-padding width |
| next_bates | INTEGER | NOT NULL, DEFAULT 1 | Next available Bates number |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'draft'` | `draft`, `finalized`, `produced` |
| created_by | UUID | NOT NULL | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_production_sets_matter_id` on (`matter_id`)

**Unique constraint:** `uq_production_sets_matter_name` on (`matter_id`, `name`)

---

#### `production_set_documents`

Join table: assigns documents to production sets with Bates stamps.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| production_set_id | UUID | FK -> production_sets.id ON DELETE CASCADE, NOT NULL | |
| document_id | UUID | FK -> documents.id ON DELETE CASCADE, NOT NULL | |
| bates_begin | VARCHAR(100) | NULLABLE | Assigned Bates begin number |
| bates_end | VARCHAR(100) | NULLABLE | Assigned Bates end number |
| added_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Unique constraint:** `uq_psd_set_document` on (`production_set_id`, `document_id`)

---

#### `export_jobs`

Tracks export/download jobs for production sets or query results.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | NOT NULL | |
| export_type | VARCHAR(50) | NOT NULL | e.g., `production`, `search_results`, `report` |
| export_format | VARCHAR(20) | NOT NULL, DEFAULT `'zip'` | |
| status | VARCHAR(50) | NOT NULL, DEFAULT `'pending'` | |
| parameters | JSONB | NOT NULL, DEFAULT `'{}'::jsonb` | Export configuration |
| output_path | VARCHAR(500) | NULLABLE | MinIO path to output file |
| file_size_bytes | BIGINT | NULLABLE | |
| error | TEXT | NULLABLE | |
| created_by | UUID | NOT NULL | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| completed_at | TIMESTAMPTZ | NULLABLE | |

**Indexes:**
- `ix_export_jobs_matter_id` on (`matter_id`)

---

### Redaction

#### `redactions`

Append-only redaction records. Each row represents a single redacted span.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| document_id | UUID | FK -> documents.id ON DELETE CASCADE, NOT NULL | |
| matter_id | UUID | NOT NULL | |
| user_id | UUID | NOT NULL | |
| redaction_type | VARCHAR(20) | NOT NULL | e.g., `manual`, `pii_auto`, `privilege` |
| pii_category | VARCHAR(20) | NULLABLE | e.g., `ssn`, `phone`, `email`, `address` |
| page_number | INTEGER | NULLABLE | |
| span_start | INTEGER | NULLABLE | Character offset start |
| span_end | INTEGER | NULLABLE | Character offset end |
| reason | TEXT | NOT NULL | Justification for redaction |
| original_text_hash | VARCHAR(64) | NOT NULL | SHA-256 of redacted text (for audit, NOT the text itself) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_redactions_document` on (`document_id`, `matter_id`)
- `ix_redactions_created` on (`created_at`)

---

### Evaluation

#### `evaluation_dataset_items`

Ground-truth question-answer pairs for RAG evaluation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| dataset_type | VARCHAR(50) | NOT NULL | e.g., `factoid`, `multi_hop`, `temporal` |
| question | TEXT | NOT NULL | |
| expected_answer | TEXT | NOT NULL | |
| tags | JSON | NOT NULL, DEFAULT `'[]'::jsonb` | Categorization tags |
| metadata_ | JSON | NOT NULL, DEFAULT `'{}'::jsonb` | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- Index on (`dataset_type`) -- created inline via `index=True`

---

#### `evaluation_runs`

Tracks evaluation pipeline executions and aggregate metrics.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| mode | VARCHAR(20) | NOT NULL, DEFAULT `'full'` | `full`, `quick`, `subset` |
| status | VARCHAR(20) | NOT NULL, DEFAULT `'pending'` | |
| metrics | JSON | NULLABLE | Aggregate metrics (precision, recall, etc.) |
| config_overrides | JSON | NOT NULL, DEFAULT `'{}'::jsonb` | Overrides applied for this run |
| total_items | INTEGER | NOT NULL, DEFAULT 0 | |
| processed_items | INTEGER | NOT NULL, DEFAULT 0 | |
| error | TEXT | NULLABLE | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| completed_at | TIMESTAMPTZ | NULLABLE | |

---

### Datasets

#### `datasets`

Folder-tree structure for organizing documents within a matter.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| matter_id | UUID | FK -> case_matters.id ON DELETE CASCADE, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | |
| description | TEXT | NOT NULL, DEFAULT `''` | |
| parent_id | UUID | FK -> datasets.id ON DELETE CASCADE, NULLABLE | Self-referential for nesting |
| created_by | UUID | FK -> users.id, NULLABLE | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_datasets_matter_id` on (`matter_id`)
- `ix_datasets_parent_id` on (`parent_id`)

**Unique constraint:** `uq_datasets_matter_parent_name` on (`matter_id`, `parent_id`, `name`)

---

#### `dataset_documents`

Many-to-many junction: assigns documents to datasets.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| dataset_id | UUID | PK (composite), FK -> datasets.id ON DELETE CASCADE | |
| document_id | UUID | PK (composite), FK -> documents.id ON DELETE CASCADE | |
| assigned_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| assigned_by | UUID | FK -> users.id, NULLABLE | |

**Indexes:**
- `ix_dataset_documents_document_id` on (`document_id`)

---

#### `document_tags`

Cross-cutting labels on documents.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| document_id | UUID | PK (composite), FK -> documents.id ON DELETE CASCADE | |
| tag_name | VARCHAR(100) | PK (composite) | |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| created_by | UUID | FK -> users.id, NULLABLE | |

**Indexes:**
- `ix_document_tags_tag_name` on (`tag_name`)

---

#### `dataset_access`

Per-dataset permission overrides.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| dataset_id | UUID | FK -> datasets.id ON DELETE CASCADE, NOT NULL | |
| user_id | UUID | FK -> users.id ON DELETE CASCADE, NOT NULL | |
| access_role | VARCHAR(20) | NOT NULL, DEFAULT `'viewer'` | `viewer`, `editor`, `admin` |
| granted_by | UUID | FK -> users.id, NULLABLE | |
| granted_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes:**
- `ix_dataset_access_dataset_id` on (`dataset_id`)

**Unique constraint:** `uq_dataset_access_dataset_user` on (`dataset_id`, `user_id`)

---

## LangGraph

LangGraph uses its own tables for checkpoint persistence via `PostgresCheckpointer`. These tables are managed by LangGraph itself (not via Alembic migrations) and are created automatically when the checkpointer is initialized. They are not documented here as their schema is internal to the `langgraph-checkpoint-postgres` library.

---

## Notes

- **Matter scoping:** All data-bearing tables include a `matter_id` column. Every query must filter by matter.
- **Immutable audit tables:** `audit_log`, `ai_audit_log`, and `agent_audit_log` are protected by PostgreSQL RULEs that silently discard UPDATE and DELETE operations (SOC 2 compliance).
- **No ORM:** All SQL is written as raw queries via `sqlalchemy.text()` with named `:param` bind parameters.
- **Timestamps:** All `created_at` / `updated_at` columns are `TIMESTAMPTZ` (timezone-aware) with `DEFAULT now()`.
- **UUIDs:** All primary keys are `UUID` with `DEFAULT gen_random_uuid()` (PostgreSQL built-in).
- **JSONB vs JSON:** Early migrations use `JSONB` (from `sqlalchemy.dialects.postgresql`); later migrations use `JSON` with `::jsonb` casts. Both produce `jsonb` columns in PostgreSQL.
