# Module Reference Guide

NEXUS has 16 domain modules under `app/`, plus a shared `app/common/` infrastructure module. Each domain follows the standard structure: `router.py` (endpoints), `service.py` (business logic), `schemas.py` (Pydantic models), `tasks.py` (Celery background work). Not every module has all four files -- the actual contents depend on the domain's needs.

---

## app/analysis/

**Purpose**: Sentiment analysis, hot document detection, completeness analysis, and communication anomaly detection. Uses Instructor + LLM to score documents across Fraud Triangle dimensions and flag investigatively significant "hot docs".

### Files

| File | Description |
|------|-------------|
| `schemas.py` | SentimentDimensions, HotDocSignals, DocumentSentimentResult, CompletenessResult, AnomalyResult |
| `tasks.py` | Celery tasks: `scan_document_sentiment` (per-doc), `scan_matter_hot_docs` (batch dispatch) |
| `sentiment.py` | `SentimentScorer` -- Instructor-based 7-dimension sentiment + hot doc scoring |
| `completeness.py` | `CompletenessAnalyzer` -- detects context gaps (missing attachments, coded language, etc.) |
| `anomaly.py` | `CommunicationBaseline` -- statistical anomaly detection against per-person baselines |
| `prompts.py` | `SENTIMENT_SCORING_PROMPT`, `COMPLETENESS_ANALYSIS_PROMPT` |

### Key Schemas

- `SentimentDimensions` -- 7-dimension float scores (positive, negative, pressure, opportunity, rationalization, intent, concealment)
- `HotDocSignals` -- 3 supplementary signals (admission_guilt, inappropriate_enthusiasm, deliberate_vagueness)
- `DocumentSentimentResult` -- LLM response model combining sentiment + signals + hot_doc_score
- `CompletenessResult` -- context_gap_score + list of ContextGap detections
- `ContextGapType` -- StrEnum: missing_attachment, prior_conversation, forward_reference, coded_language, unusual_terseness
- `AnomalyResult` -- anomaly_score + per-dimension deviations
- `PersonBaseline` -- avg_message_length, message_count, tone_profile

### Endpoints

- None (no router). Analysis is triggered via Celery tasks from the ingestion pipeline or ad-hoc.

### Feature Flags

- `ENABLE_HOT_DOC_DETECTION` (default: `false`) -- gates the sentiment analysis pipeline

### Dependencies

- Uses: Qdrant (fetch chunk texts), PostgreSQL (persist scores), Instructor + LLM (scoring)
- Called by: `app/ingestion/tasks.py` (post-ingestion)

### Tests

- `tests/test_analysis/` -- 6 test files

---

## app/analytics/

**Purpose**: Communication network analytics -- sender/recipient matrices from email metadata, Neo4j GDS centrality rankings, org chart import, hierarchy inference, and BERTopic topic clustering.

### Files

| File | Description |
|------|-------------|
| `router.py` | GET /analytics/communication-matrix, GET /analytics/network-centrality |
| `service.py` | `AnalyticsService` -- communication pair extraction, matrix queries, centrality, org chart import/inference |
| `schemas.py` | CommunicationPair, CentralityMetric, OrgChartEntry, TopicCluster, etc. |
| `clustering.py` | `TopicClusterer` -- lazy-loaded BERTopic wrapper for unsupervised topic clustering |

### Key Schemas

- `CentralityMetric` -- StrEnum: degree, pagerank, betweenness
- `CommunicationPair` -- sender/recipient with message_count, earliest/latest dates
- `CommunicationMatrixResponse` -- full matrix with total_messages, unique_senders/recipients
- `EntityCentrality` -- name, type, score, rank
- `NetworkCentralityResponse` -- ranked entity centrality for a matter
- `OrgChartEntry` -- person/reporting relationship with title, department, source, confidence
- `OrgChartImportRequest` / `OrgChartImportResponse`
- `TopicCluster` -- topic_id, label, representative_terms, document_count
- `TopicClusterResponse`

### Endpoints

- `GET /api/v1/analytics/communication-matrix` -- pre-computed sender-recipient pairs (filterable by entity)
- `GET /api/v1/analytics/network-centrality` -- Neo4j GDS centrality rankings (degree/pagerank/betweenness)

### Feature Flags

- `ENABLE_TOPIC_CLUSTERING` (default: `false`) -- gates BERTopic clustering
- `ENABLE_GRAPH_CENTRALITY` (default: `false`) -- gates Neo4j GDS centrality

### Dependencies

- Uses: `app/entities/graph_service.py` (centrality queries), PostgreSQL (communication_pairs table)
- Called by: `app/cases/router.py` (org chart import endpoint)

### Tests

- `tests/test_analytics/` -- 6 test files

---

## app/annotations/

**Purpose**: Document annotation management -- notes, highlights, and tags that users attach to specific documents and pages.

### Files

| File | Description |
|------|-------------|
| `router.py` | Full CRUD: POST, GET, GET/{id}, PATCH/{id}, DELETE/{id} for annotations |
| `service.py` | `AnnotationService` -- CRUD operations against the `annotations` table |
| `schemas.py` | AnnotationType, AnnotationCreate, AnnotationUpdate, AnnotationResponse, AnnotationListResponse |

### Key Schemas

- `AnnotationType` -- StrEnum: note, highlight, tag
- `AnnotationCreate` -- document_id, page_number, annotation_type, content, anchor (JSONB), color
- `AnnotationUpdate` -- optional fields for partial update
- `AnnotationResponse` -- full annotation with id, timestamps, user_id
- `AnnotationListResponse` -- paginated (extends `PaginatedResponse[AnnotationResponse]`)

### Endpoints

- `POST /api/v1/annotations` -- create annotation on a document
- `GET /api/v1/annotations` -- list annotations (filter by document_id)
- `GET /api/v1/annotations/{annotation_id}` -- get single annotation
- `PATCH /api/v1/annotations/{annotation_id}` -- update (owner only)
- `DELETE /api/v1/annotations/{annotation_id}` -- delete (owner only)

### Feature Flags

- None (core functionality)

### Dependencies

- Uses: PostgreSQL (`annotations` table), `app/common/db_utils.py`, `app/common/models.py`
- Validates document belongs to matter before creating annotations

### Tests

- `tests/test_annotations/` -- 1 test file

---

## app/audit/

**Purpose**: SOC 2 audit trail -- AI interaction logging, agent action logging, request audit logging, CSV/JSON export, and retention policy management. Admin-only endpoints.

### Files

| File | Description |
|------|-------------|
| `router.py` | GET /admin/audit/ai, GET /admin/audit/export, GET /admin/audit/retention, POST /admin/audit/retention |
| `service.py` | `AuditService` -- log_request, log_ai_call, log_agent_action, list/export/retention operations |
| `schemas.py` | AIAuditLogEntry, AgentAuditLogEntry, RetentionConfig, ExportFormat |

### Key Schemas

- `AIAuditLogEntry` -- request_id, session_id, node_name, provider, model, token counts, latency_ms, status
- `AgentAuditLogEntry` -- agent_id, action_type, action_name, iteration_number, duration_ms
- `RetentionConfig` -- retention_days (min 30 for SOC 2), current_count, oldest_entry, entries_beyond_retention
- `ExportFormat` -- StrEnum: csv, json
- `AIAuditLogListResponse` -- paginated list

### Endpoints

- `GET /api/v1/admin/audit/ai` -- paginated AI audit log (filterable by session_id, node_name, provider, date range)
- `GET /api/v1/admin/audit/export` -- export audit logs as CSV or JSON (supports ai_audit_log, agent_audit_log, audit_log)
- `GET /api/v1/admin/audit/retention` -- retention status for AI audit log
- `POST /api/v1/admin/audit/retention` -- dry-run retention policy (returns count of entries to archive)

### Feature Flags

- `ENABLE_AI_AUDIT_LOGGING` (default: `true`) -- gates AI call logging

### Dependencies

- Uses: PostgreSQL (`ai_audit_log`, `agent_audit_log`, `audit_log` tables)
- Called by: `app/common/middleware.py` (request audit), `app/query/nodes.py` (AI call audit)

### Tests

- `tests/test_audit/` -- 1 test file

---

## app/auth/

**Purpose**: Authentication and authorization -- JWT access/refresh tokens, API key auth, RBAC with 4 roles (admin, attorney, paralegal, reviewer), matter scoping, user CRUD, audit log viewer.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /auth/login, POST /auth/refresh, GET /auth/me, GET /auth/me/matters |
| `admin_router.py` | GET /admin/audit-log, GET/POST /admin/users, PATCH/DELETE /admin/users/{id} |
| `service.py` | `AuthService` -- password hashing (bcrypt), JWT create/decode, user CRUD, matter access checks |
| `middleware.py` | `get_current_user` (Bearer + API key), `require_role`, `get_matter_id` (X-Matter-ID header) |
| `schemas.py` | Role, LoginRequest, TokenResponse, UserRecord, UserResponse, UserCreateRequest, MatterResponse, AuditLogEntry |

### Key Schemas

- `Role` -- StrEnum: admin, attorney, paralegal, reviewer
- `LoginRequest` -- email + password
- `TokenResponse` -- access_token, refresh_token, token_type, expires_in
- `UserRecord` -- internal record with password_hash and api_key_hash
- `UserResponse` -- public user profile
- `UserCreateRequest` -- email, password (min 8), full_name, role
- `UserUpdateRequest` -- optional fields for admin updates
- `MatterResponse` -- id, name, description, is_active
- `AuditLogEntry` -- user_id, action, resource, matter_id, ip_address, status_code

### Endpoints

- `POST /api/v1/auth/login` -- JWT token issuance
- `POST /api/v1/auth/refresh` -- token refresh
- `GET /api/v1/auth/me` -- current user profile
- `GET /api/v1/auth/me/matters` -- matters accessible to current user
- `GET /api/v1/admin/audit-log` -- filterable audit log (admin-only)
- `GET /api/v1/admin/users` -- list users (admin/attorney)
- `POST /api/v1/admin/users` -- create user (admin-only)
- `PATCH /api/v1/admin/users/{user_id}` -- update user (admin-only)
- `DELETE /api/v1/admin/users/{user_id}` -- deactivate user (admin-only)

### Feature Flags

- None (core functionality)

### Dependencies

- Uses: PostgreSQL (`users`, `case_matters`, `user_case_matters` tables), bcrypt, PyJWT
- Used by: All other modules via `get_current_user`, `get_matter_id`, `require_role` dependencies

### Tests

- `tests/test_auth/` -- 4 test files

---

## app/cases/

**Purpose**: Case intelligence layer -- anchor document (complaint) upload, LangGraph Case Setup Agent for extracting claims/parties/defined terms/timeline, case context CRUD, org chart import, query-time context resolution.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /cases/{matter_id}/setup, GET/PATCH /cases/{matter_id}/context, POST /cases/{matter_id}/org-chart |
| `service.py` | `CaseService` -- CRUD for case_contexts, case_claims, case_parties, case_defined_terms, investigation_sessions |
| `schemas.py` | API schemas (CaseSetupResponse, ClaimResponse, PartyResponse, etc.) + Instructor extraction models (ExtractedClaim, etc.) |
| `agent.py` | `build_case_setup_graph` -- LangGraph StateGraph with 6 nodes: parse, extract claims/parties/terms, build timeline, populate graph |
| `tasks.py` | `run_case_setup` Celery task -- wraps the LangGraph agent |
| `prompts.py` | 4 extraction prompts: EXTRACT_CLAIMS_PROMPT, EXTRACT_PARTIES_PROMPT, EXTRACT_DEFINED_TERMS_PROMPT, EXTRACT_TIMELINE_PROMPT |
| `context_resolver.py` | `CaseContextResolver` -- builds term/alias maps and expands references in queries at runtime |

### Key Schemas

- `CaseSetupResponse` -- job_id, case_context_id, status, created_at
- `CaseContextResponse` -- full context with claims, parties, defined_terms, timeline
- `ClaimResponse` / `ClaimInput` -- claim_number, claim_label, claim_text, legal_elements, source_pages
- `PartyResponse` / `PartyInput` -- name, role (PartyRole), description, aliases, entity_id
- `DefinedTermResponse` / `DefinedTermInput` -- term, definition, entity_id
- `TimelineEvent` -- date, event_text, source_page
- `CaseContextUpdateRequest` -- PATCH body with optional claims/parties/terms/timeline
- `ExtractedClaim`, `ExtractedParty`, `ExtractedDefinedTerm`, `ExtractedTimeline` -- Instructor extraction models
- `InvestigationSessionResponse`

### Endpoints

- `POST /api/v1/cases/{matter_id}/setup` -- upload anchor doc, start case setup (admin/attorney)
- `GET /api/v1/cases/{matter_id}/context` -- get full case context
- `PATCH /api/v1/cases/{matter_id}/context` -- edit/confirm extracted context (admin/attorney)
- `POST /api/v1/cases/{matter_id}/org-chart` -- import org chart entries (admin/attorney)

### Feature Flags

- `ENABLE_CASE_SETUP_AGENT` (default: `false`) -- gates the LangGraph case setup pipeline

### Dependencies

- Uses: `app/ingestion/service.py` (job creation), `app/ingestion/parser.py` (document parsing), MinIO (file storage), Neo4j (party/claim graph nodes), Instructor + LLM (extraction), `app/analytics/service.py` (org chart import)
- Used by: `app/query/nodes.py` (case context resolution at query time)

### Tests

- `tests/test_cases/` -- 5 test files

---

## app/common/

**Purpose**: Shared infrastructure -- cross-cutting utilities used by all domain modules. Not a domain module itself; has no router or endpoints.

### Files

| File | Description |
|------|-------------|
| `middleware.py` | `RequestIDMiddleware`, `RequestLoggingMiddleware`, `AuditLoggingMiddleware`, CORS configuration |
| `storage.py` | `StorageClient` -- async boto3 wrapper for MinIO/S3 (upload, download, presigned URLs) |
| `llm.py` | `LLMClient` -- unified async client for Anthropic/OpenAI/vLLM/Ollama with retry, streaming, audit logging |
| `vector_store.py` | `VectorStoreClient` -- Qdrant client wrapper managing `nexus_text` + `nexus_visual` collections with named vectors and native RRF fusion |
| `embedder.py` | `EmbeddingProvider` protocol + `OpenAIEmbeddingProvider` + `LocalEmbeddingProvider` (sentence-transformers) with audit logging |
| `rate_limit.py` | Redis sliding-window rate limiter via sorted sets: `rate_limit_queries`, `rate_limit_ingests` |
| `models.py` | Shared enums (`JobStatus`, `PrivilegeStatus`, `CaseStatus`, `PartyRole`, `DocumentType`), `TimestampMixin`, `PaginatedResponse[T]` |
| `db_utils.py` | `parse_jsonb`, `row_to_dict` -- SQL result helpers |

### Key Classes

- `LLMClient` -- `generate()`, `stream()`, `generate_with_instructor()` with automatic tenacity retry and prompt hashing for audit
- `StorageClient` -- `upload_bytes()`, `download_bytes()`, `get_presigned_url()`, `get_presigned_put_url()`
- `VectorStoreClient` -- `ensure_collections()`, `upsert_chunks()`, `search()` with dense+sparse RRF fusion
- `EmbeddingProvider` -- Protocol with `embed_texts()` and `embed_query()`
- `OpenAIEmbeddingProvider` -- OpenAI API with batch support and SHA-256 audit hashing
- `LocalEmbeddingProvider` -- on-device sentence-transformers (no data leaves the machine)
- `PaginatedResponse[T]` -- generic envelope: items, total, offset, limit

### Feature Flags

- None (always available)

### Dependencies

- Used by: All domain modules

### Tests

- `tests/test_common/` -- 8 test files

---

## app/datasets/

**Purpose**: Dataset and collection management -- hierarchical folder system for organizing documents, document tagging, dataset-scoped access control, query scoping to datasets.

### Files

| File | Description |
|------|-------------|
| `router.py` | Full CRUD for datasets, document assignment/move, tags, access control (23 endpoints) |
| `service.py` | `DatasetService` -- dataset CRUD, recursive CTE tree queries, document assignment, tag operations, ACL management |
| `schemas.py` | DatasetCreateRequest, DatasetTreeNode, AssignDocumentsRequest, TagRequest, DatasetAccessRequest, etc. |

### Key Schemas

- `DatasetAccessRole` -- StrEnum: viewer, editor, admin
- `DatasetCreateRequest` -- name, description, parent_id (for nesting)
- `DatasetResponse` -- id, matter_id, name, parent_id, document_count, children_count
- `DatasetTreeNode` -- recursive model with children list
- `DatasetTreeResponse` -- roots + total_datasets
- `DatasetListResponse` -- paginated
- `AssignDocumentsRequest` -- list of document_ids (max 500)
- `MoveDocumentsRequest` -- document_ids + target_dataset_id
- `TagRequest` -- tag_name (alphanumeric pattern)
- `TagResponse` -- tag_name + document_count
- `DocumentTagsResponse` -- document_id + tag list
- `DatasetAccessRequest` -- user_id + access_role
- `DatasetAccessResponse`

### Endpoints

- `POST /api/v1/datasets` -- create dataset (folder)
- `GET /api/v1/datasets` -- list datasets (flat, paginated)
- `GET /api/v1/datasets/tree` -- full folder tree (recursive CTE)
- `GET /api/v1/datasets/{id}` -- single dataset with counts
- `PATCH /api/v1/datasets/{id}` -- update name/description/parent (move)
- `DELETE /api/v1/datasets/{id}` -- delete with cascade (admin/attorney)
- `POST /api/v1/datasets/{id}/documents` -- assign documents
- `DELETE /api/v1/datasets/{id}/documents` -- unassign documents
- `POST /api/v1/datasets/{id}/documents/move` -- move to another dataset
- `GET /api/v1/datasets/{id}/documents` -- list documents in dataset
- `POST /api/v1/documents/{id}/tags` -- add tag
- `DELETE /api/v1/documents/{id}/tags/{tag_name}` -- remove tag
- `GET /api/v1/documents/{id}/tags` -- list tags on document
- `GET /api/v1/tags` -- all tags in matter (autocomplete)
- `GET /api/v1/tags/{tag_name}/documents` -- documents with tag
- `POST /api/v1/datasets/{id}/access` -- grant access (admin/attorney)
- `DELETE /api/v1/datasets/{id}/access/{user_id}` -- revoke access (admin/attorney)
- `GET /api/v1/datasets/{id}/access` -- list access entries (admin/attorney)

### Feature Flags

- None (core functionality)

### Dependencies

- Uses: PostgreSQL (`datasets`, `dataset_documents`, `document_tags`, `dataset_access` tables)
- Used by: `app/query/retriever.py` (dataset-scoped Qdrant filtering), `app/documents/router.py` (dataset/tag filters)

### Tests

- `tests/test_datasets/` -- 2 test files

---

## app/documents/

**Purpose**: Document metadata management -- list, view, preview, download, and privilege tagging for ingested documents. Thin CRUD layer over the `documents` table.

### Files

| File | Description |
|------|-------------|
| `router.py` | GET /documents (filterable), GET /{id}, GET /{id}/preview, GET /{id}/download, PATCH /{id}/privilege |
| `service.py` | `DocumentService` -- list with filters (type, filename, hot_doc_score, anomaly_score, dataset, tag), get, privilege updates across PG+Qdrant+Neo4j |
| `schemas.py` | DocumentResponse, DocumentDetail, DocumentPreview, PrivilegeUpdateRequest, PrivilegeUpdateResponse |

### Key Schemas

- `DocumentResponse` -- id, filename, type, page_count, chunk_count, entity_count, minio_path, privilege_status, thread_id, duplicate_cluster_id, version_group_id
- `DocumentDetail` -- extends DocumentResponse with metadata_, file_size_bytes, content_hash, message_id, in_reply_to, thread_position, duplicate_score, version_number, is_final_version
- `DocumentPreview` -- doc_id, page, image_url (presigned)
- `DocumentListResponse` -- paginated
- `PrivilegeStatus` -- (from common/models) StrEnum: privileged, work_product, confidential, not_privileged
- `PrivilegeUpdateRequest` -- privilege_status
- `PrivilegeUpdateResponse` -- id, privilege_status, reviewed_by, reviewed_at

### Endpoints

- `GET /api/v1/documents` -- list documents (filters: document_type, q, hot_doc_score_min, anomaly_score_min, dataset_id, tag_name)
- `GET /api/v1/documents/{doc_id}` -- document metadata detail
- `GET /api/v1/documents/{doc_id}/preview` -- page thumbnail presigned URL
- `GET /api/v1/documents/{doc_id}/download` -- original file presigned URL
- `PATCH /api/v1/documents/{doc_id}/privilege` -- update privilege status (admin/attorney/paralegal)

### Feature Flags

- None (core functionality)

### Dependencies

- Uses: PostgreSQL (`documents` table), MinIO (presigned URLs), Qdrant (privilege propagation), Neo4j (privilege propagation)

### Tests

- `tests/test_documents/` -- 4 test files

---

## app/edrm/

**Purpose**: EDRM (Electronic Discovery Reference Model) interoperability -- import/export of industry-standard load files (Concordance DAT, Opticon OPT, EDRM XML), email thread listing, and duplicate cluster browsing.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /edrm/import, GET /edrm/export, GET /edrm/threads, GET /edrm/duplicates |
| `service.py` | `EDRMService` -- thread listing, duplicate cluster listing, import log CRUD |
| `schemas.py` | LoadFileFormat, ImportStatus, LoadFileRecord, OpticonRecord, EDRMImportResponse, ThreadResponse, DuplicateCluster |
| `loadfile_parser.py` | `LoadFileParser` -- parse_dat (Concordance), parse_opt (Opticon), parse_edrm_xml, export_edrm_xml |

### Key Schemas

- `LoadFileFormat` -- StrEnum: concordance_dat, opticon_opt, edrm_xml
- `ImportStatus` -- StrEnum: pending, processing, complete, failed
- `LoadFileRecord` -- doc_id + fields dict
- `OpticonRecord` -- doc_id, volume, image_path, document_break, box_or_folder, pages
- `EDRMImportResponse` -- import_id, status, record_count, message
- `EDRMImportLogEntry` -- full import log record
- `ThreadResponse` -- thread_id, message_count, earliest, latest
- `ThreadListResponse` -- paginated
- `DuplicateCluster` -- cluster_id, document_count, avg_score
- `DuplicateClusterListResponse` -- paginated

### Endpoints

- `POST /api/v1/edrm/import` -- import a load file (DAT/OPT/XML), imports Bates numbers
- `GET /api/v1/edrm/export` -- export matter documents as EDRM XML
- `GET /api/v1/edrm/threads` -- list email threads with message counts
- `GET /api/v1/edrm/duplicates` -- list near-duplicate clusters

### Feature Flags

- `ENABLE_EMAIL_THREADING` (default: `true`) -- gates thread detection during ingestion
- `ENABLE_NEAR_DUPLICATE_DETECTION` (default: `false`) -- gates duplicate detection during ingestion

### Dependencies

- Uses: PostgreSQL (documents, edrm_import_log tables), `app/exports/service.py` (Bates import)

### Tests

- `tests/test_edrm/` -- 4 test files

---

## app/entities/

**Purpose**: Entity extraction, knowledge graph management, and entity resolution. Zero-shot NER via GLiNER, relationship extraction via Instructor+LLM, cross-document entity resolution, Neo4j graph operations, and a LangGraph resolution agent.

### Files

| File | Description |
|------|-------------|
| `router.py` | GET /entities, /{id}, /{id}/connections, /graph/explore, /graph/timeline, /graph/stats, /graph/communication-pairs, /graph/reporting-chain, /graph/path |
| `extractor.py` | `EntityExtractor` -- GLiNER zero-shot NER (~600MB model, CPU, 12 entity types) |
| `relationship_extractor.py` | `RelationshipExtractor` -- Instructor + Claude for tier-2 relationship extraction on entity-rich chunks |
| `graph_service.py` | `GraphService` -- Neo4j async wrapper: create/merge entity/document/email nodes, search, connections, timeline, communication pairs, centrality, path-finding |
| `resolver.py` | `EntityResolver` -- cross-document dedup using rapidfuzz + embedding cosine similarity + union-find |
| `resolution_agent.py` | `build_resolution_graph` -- LangGraph StateGraph for deterministic post-ingestion entity dedup pipeline |
| `tasks.py` | `resolve_entities` Celery task -- runs fuzzy matching and merges duplicate entities |
| `coreference.py` | `CoreferenceResolver` -- spaCy + coreferee for pronoun resolution before NER |
| `schema.py` | Neo4j schema management: `ENTITY_TYPE_TO_LABEL`, `ensure_schema()`, `migrate_existing_entities()`, email header parsing |
| `schemas.py` | EntityResponse, EntityConnection, GraphStatsResponse, TimelineEvent, CommunicationPairRecord, PathResponse |

### Key Schemas

- `EntityResponse` -- id, name, type, aliases, first_seen, last_seen, description, mention_count
- `EntityConnection` -- source, target, relationship_type, context, weight
- `GraphStatsResponse` -- node_count, edge_count, entity_types dict
- `TimelineEvent` -- date, description, entities, document_source
- `CommunicationPairsResponse` -- person_a, person_b, emails list
- `ReportingChainResponse` -- person + chains
- `PathResponse` -- entity_a, entity_b, paths
- `ExtractedRelationship` (in relationship_extractor) -- source/target entities + types, relationship_type, context, confidence, temporal
- `ExtractedEntity` (in extractor) -- text, type, score, start, end

### Endpoints

- `GET /api/v1/entities` -- search/list entities (filterable by name, type)
- `GET /api/v1/entities/{entity_id}` -- entity details by name
- `GET /api/v1/entities/{entity_id}/connections` -- graph neighbourhood (privilege-filtered)
- `GET /api/v1/graph/explore` -- read-only Cypher queries (write keywords blocked)
- `GET /api/v1/graph/timeline/{entity}` -- chronological events for an entity
- `GET /api/v1/graph/stats` -- node and edge counts
- `GET /api/v1/graph/communication-pairs` -- emails between two people (date-filterable)
- `GET /api/v1/graph/reporting-chain/{person}` -- REPORTS_TO chain
- `GET /api/v1/graph/path` -- shortest path between two entities (configurable max_hops and relationship types)

### Feature Flags

- `ENABLE_RELATIONSHIP_EXTRACTION` (default: `false`) -- gates tier-2 Instructor+LLM relationship extraction
- `ENABLE_COREFERENCE_RESOLUTION` (default: `false`) -- gates spaCy + coreferee pronoun resolution

### Dependencies

- Uses: Neo4j (graph storage), GLiNER (NER model), Instructor + LLM (relationship extraction), rapidfuzz + networkx (resolution), spaCy + coreferee (coreference)
- Used by: `app/ingestion/tasks.py` (entity extraction during ingestion), `app/query/retriever.py` (graph retrieval)

### Tests

- `tests/test_entities/` -- 7 test files

---

## app/evaluation/

**Purpose**: RAG evaluation framework -- manage ground-truth datasets, trigger evaluation runs, track metrics (accuracy, faithfulness, relevance, citation precision/recall, latency).

### Files

| File | Description |
|------|-------------|
| `router.py` | GET /evaluation/latest, GET/POST/DELETE /evaluation/datasets/{type}, GET/POST /evaluation/runs |
| `service.py` | `EvaluationService` -- dataset item CRUD, run management, metrics computation |
| `schemas.py` | DatasetType, EvalRunStatus, EvalMode, DatasetItemCreate, EvalMetrics, EvalRunResponse, LatestEvalResponse |

### Key Schemas

- `DatasetType` -- StrEnum: ground_truth, adversarial, legal_bench
- `EvalRunStatus` -- StrEnum: pending, running, completed, failed
- `EvalMode` -- StrEnum: full, quick, custom
- `DatasetItemCreate` -- question, expected_answer, tags, metadata_
- `DatasetItemResponse` -- id, dataset_type, question, expected_answer, tags, metadata_, created_at
- `EvalMetrics` -- accuracy, faithfulness, relevance, citation_precision, citation_recall, latency_p50_ms, latency_p95_ms
- `EvalRunResponse` -- id, mode, status, metrics, config_overrides, total_items, processed_items, error
- `LatestEvalResponse` -- metrics, passed, run_id, completed_at
- `RunCreateRequest` -- mode, config_overrides

### Endpoints

- `GET /api/v1/evaluation/latest` -- metrics from most recent completed run (admin-only)
- `GET /api/v1/evaluation/datasets/{dataset_type}` -- list dataset items (admin-only)
- `POST /api/v1/evaluation/datasets/{dataset_type}` -- create dataset item (admin-only)
- `DELETE /api/v1/evaluation/datasets/{dataset_type}/{item_id}` -- delete dataset item (admin-only)
- `GET /api/v1/evaluation/runs` -- list evaluation runs (admin-only)
- `POST /api/v1/evaluation/runs` -- trigger new evaluation run (admin-only)

### Feature Flags

- None (admin-only functionality)

### Dependencies

- Uses: PostgreSQL (`evaluation_dataset_items`, `evaluation_runs` tables)

### Tests

- `tests/test_evaluation/` -- 7 test files

---

## app/exports/

**Purpose**: Production set management and document export -- Bates numbering, court-ready PDF packages, EDRM XML export, privilege log generation, background export via Celery.

### Files

| File | Description |
|------|-------------|
| `router.py` | Production set CRUD, document assignment, Bates numbering, export job creation/listing/download, privilege log preview |
| `service.py` | `ExportService` -- production set CRUD, Bates assignment, export job management, privilege log queries, Bates import from load files |
| `schemas.py` | ExportType, ExportFormat, ProductionSetCreate, ProductionSetResponse, ExportRequest, ExportJobResponse, PrivilegeLogEntry |
| `generators.py` | Format-specific generators: court_ready (ZIP), EDRM XML, privilege log (CSV/XLSX), result set (CSV) |
| `tasks.py` | `run_export` Celery task -- dispatches to format generators, uploads to MinIO |

### Key Schemas

- `ExportType` -- StrEnum: court_ready, edrm_xml, privilege_log, result_set
- `ExportFormat` -- StrEnum: zip, csv, xlsx
- `ExportStatus` -- StrEnum: pending, processing, complete, failed
- `ProductionSetStatus` -- StrEnum: draft, finalized, exported
- `BatesMode` -- StrEnum: auto, prefix_start, imported
- `ProductionSetCreate` -- name, description, bates_prefix, bates_start, bates_padding
- `ProductionSetResponse` -- full set with next_bates, status, document_count
- `ProductionSetAddDocuments` -- list of document_ids
- `ProductionSetDocumentResponse` -- bates_begin, bates_end, filename
- `ExportRequest` -- export_type, export_format, document_ids, production_set_id, parameters
- `ExportJobResponse` -- id, status, output_path, file_size_bytes
- `PrivilegeLogEntry` -- bates_begin/end, filename, doc_type, privilege_status, privilege_basis

### Endpoints

- `POST /api/v1/exports/production-sets` -- create production set (admin/attorney/paralegal)
- `GET /api/v1/exports/production-sets` -- list production sets
- `GET /api/v1/exports/production-sets/{id}` -- get production set
- `POST /api/v1/exports/production-sets/{id}/documents` -- add documents to production set
- `GET /api/v1/exports/production-sets/{id}/documents` -- list documents in production set
- `DELETE /api/v1/exports/production-sets/{id}/documents/{doc_id}` -- remove document
- `POST /api/v1/exports/production-sets/{id}/assign-bates` -- assign sequential Bates numbers
- `POST /api/v1/exports` -- create export job (kicks Celery task)
- `GET /api/v1/exports/jobs` -- list export jobs
- `GET /api/v1/exports/jobs/{job_id}` -- get export job status
- `GET /api/v1/exports/jobs/{job_id}/download` -- presigned download URL
- `GET /api/v1/exports/privilege-log/preview` -- privilege log JSON preview

### Feature Flags

- None (core e-discovery functionality)

### Dependencies

- Uses: PostgreSQL (`production_sets`, `production_set_documents`, `export_jobs` tables), MinIO (export output storage), Celery (background export)

### Tests

- `tests/test_exports/` -- 1 test file

---

## app/ingestion/

**Purpose**: Document ingestion pipeline -- upload, parse, chunk, embed, extract entities, index to Qdrant/Neo4j. Supports single file, batch, webhook (MinIO), presigned upload, and bulk import from pre-parsed datasets.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /ingest, /ingest/batch, /ingest/webhook, /ingest/presigned-upload, /ingest/import/dry-run; GET/DELETE /jobs |
| `service.py` | `IngestionService` -- job CRUD, bulk import job management, dry-run estimation |
| `tasks.py` | `process_document` Celery task -- 6-stage pipeline (parse, chunk, embed, extract, index, complete) |
| `parser.py` | `DocumentParser` -- routes files to Docling (PDF/DOCX/XLSX/PPTX/HTML/images) or stdlib parsers (EML/MSG/RTF/CSV/TXT) |
| `chunker.py` | `SemanticChunker` -- tiktoken-based chunking (512 tok, 64 overlap) respecting paragraph/table boundaries |
| `embedder.py` | Re-export shim: imports `OpenAIEmbeddingProvider` from `app/common/embedder` as `TextEmbedder` |
| `sparse_embedder.py` | `SparseEmbedder` -- FastEmbed BM42 sparse embeddings (lazy-loaded) |
| `visual_embedder.py` | `VisualEmbedder` -- ColQwen2.5 multi-vector visual embeddings (lazy-loaded, 3B params) |
| `dedup.py` | `DedupDetector` -- MinHash + LSH near-duplicate detection + version tracking via datasketch |
| `threading.py` | `EmailThreader` -- RFC 5322 email threading (References/In-Reply-To/subject matching) + inclusive email detection |
| `bulk_import.py` | `ImportDocument` model, `DatasetAdapter` protocol for pre-parsed document import |
| `schemas.py` | IngestResponse, JobProgress, JobStatusResponse, BatchIngestResponse, S3EventNotification, BulkImportStatusResponse, DryRunRequest/Response, PresignedUploadRequest/Response |
| `adapters/` | Bulk import adapters: `concordance_dat.py`, `directory.py`, `edrm_xml.py` |

### Key Schemas

- `IngestResponse` -- job_id, status, filename, created_at
- `JobProgress` -- stage, pages_parsed, chunks_created, entities_extracted, embeddings_generated
- `JobStatusResponse` -- full status with progress breakdown and error
- `JobListResponse` -- paginated
- `BatchIngestResponse` -- batch_id, job_ids, filenames, total_files
- `S3EventNotification` / `S3EventRecord` -- MinIO webhook payload
- `WebhookResponse` -- status, job_ids, total
- `BulkImportStatusResponse` -- status, total/processed/failed/skipped documents, elapsed/remaining time
- `DryRunRequest` -- source_type, file_count, total_size_bytes
- `DryRunResponse` -- estimated_documents, estimated_chunks, estimated_duration_minutes, estimated_storage_mb
- `PresignedUploadRequest` / `PresignedUploadResponse`

### Endpoints

- `POST /api/v1/ingest` -- single file upload (rate-limited)
- `POST /api/v1/ingest/batch` -- multi-file upload with ZIP support (rate-limited)
- `POST /api/v1/ingest/presigned-upload` -- presigned PUT URL for direct S3 upload from browser
- `POST /api/v1/ingest/import/dry-run` -- estimate import results without processing
- `POST /api/v1/ingest/webhook` -- MinIO bucket notification handler
- `GET /api/v1/jobs/{job_id}` -- job status + progress
- `GET /api/v1/jobs` -- list all jobs (paginated)
- `DELETE /api/v1/jobs/{job_id}` -- cancel running job
- `GET /api/v1/bulk-imports/{import_id}` -- bulk import job status

### Feature Flags

- `ENABLE_SPARSE_EMBEDDINGS` (default: `false`) -- adds BM42 sparse vectors alongside dense
- `ENABLE_VISUAL_EMBEDDINGS` (default: `false`) -- adds ColQwen2.5 page-image embeddings
- `ENABLE_EMAIL_THREADING` (default: `true`) -- runs RFC 5322 threading during email ingestion
- `ENABLE_NEAR_DUPLICATE_DETECTION` (default: `false`) -- runs MinHash dedup post-ingestion

### Dependencies

- Uses: MinIO (file storage), Docling (document parsing), tiktoken (chunking), OpenAI/local embeddings, GLiNER (NER), Qdrant (vector indexing), Neo4j (graph indexing), Celery (background tasks), FastEmbed (sparse), ColQwen2.5 (visual), datasketch (dedup)
- Calls: `app/entities/extractor.py`, `app/analysis/tasks.py` (post-ingestion)

### Tests

- `tests/test_ingestion/` -- 15 test files

---

## app/query/

**Purpose**: Investigation query pipeline -- LangGraph agentic orchestration with tool-use, hybrid retrieval (Qdrant dense+sparse + Neo4j graph), cross-encoder reranking, structured cited output, SSE streaming, and chat persistence.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /query, POST /query/stream (SSE), GET /chats, GET /chats/{thread_id}, DELETE /chats/{thread_id} |
| `graph.py` | `build_graph` factory -- v1 (9-node chain) or agentic (4-node parent + create_react_agent subgraph) |
| `nodes.py` | Node functions: classify, rewrite, retrieve, rerank, check_relevance, graph_lookup, synthesize, verify_citations, generate_follow_ups, case_context_resolve, audit_log_hook |
| `retriever.py` | `HybridRetriever` -- parallel dense Qdrant search + Neo4j entity-centric graph traversal |
| `reranker.py` | `Reranker` -- lazy-loaded cross-encoder (bge-reranker-v2-m3) with MPS/CUDA/CPU auto-detect and TEI remote support |
| `tools.py` | LangGraph `@tool`-decorated functions: vector_search, graph_search, entity_lookup, timeline_query, communication_query |
| `service.py` | `QueryService` (graph state construction, response extraction) + `ChatService` (message persistence via raw SQL) |
| `prompts.py` | CLASSIFY_PROMPT, REWRITE_PROMPT, SYNTHESIS_PROMPT, FOLLOWUP_PROMPT, INVESTIGATION_SYSTEM_PROMPT, VERIFY_CLAIMS_PROMPT, VERIFY_JUDGMENT_PROMPT |
| `schemas.py` | QueryRequest, QueryResponse, SourceDocument, CitedClaim, EntityMention, ChatMessage, ChatThread, VerificationJudgment |

### Key Schemas

- `QueryRequest` -- query, thread_id, filters, dataset_id
- `QueryResponse` -- response, source_documents, follow_up_questions, entities_mentioned, thread_id, message_id, cited_claims, tier
- `SourceDocument` -- id, filename, page, chunk_text, relevance_score, preview_url, download_url
- `CitedClaim` -- claim_text, document_id, filename, page_number, bates_range, excerpt, grounding_score, verification_status
- `EntityMention` -- name, type, kg_id, connections count
- `ChatMessage` -- role, content, source_documents, entities_mentioned, follow_up_questions
- `ChatThread` -- thread_id, message_count, last_message_at, first_query
- `ChatHistoryResponse` -- thread_id + messages
- `VerificationJudgment` -- claim_index, supported, confidence, rationale

### Endpoints

- `POST /api/v1/query` -- synchronous query (full response)
- `POST /api/v1/query/stream` -- SSE streaming query (sources sent first, then token-by-token)
- `GET /api/v1/chats` -- list chat threads for current user/matter
- `GET /api/v1/chats/{thread_id}` -- full chat history
- `DELETE /api/v1/chats/{thread_id}` -- delete chat thread

### Feature Flags

- `ENABLE_RERANKER` (default: `false`) -- gates cross-encoder reranking (bge-reranker-v2-m3)
- `ENABLE_SPARSE_EMBEDDINGS` (default: `false`) -- enables native Qdrant RRF fusion with sparse vectors
- `ENABLE_AGENTIC_PIPELINE` (default: `true`) -- agentic tool-use graph vs. v1 fixed chain
- `ENABLE_CITATION_VERIFICATION` (default: `true`) -- CoVe claim verification post-synthesis
- `ENABLE_VISUAL_EMBEDDINGS` (default: `false`) -- visual reranking in retrieval

### Dependencies

- Uses: LangGraph (orchestration), Qdrant (dense+sparse search), Neo4j (graph traversal), `app/common/llm.py` (LLM calls), `app/common/embedder.py` (query embedding), `app/entities/extractor.py` (query-time NER), `app/cases/context_resolver.py` (case context), `app/datasets/service.py` (dataset scoping), Instructor (structured output), SSE-Starlette (streaming)
- Uses: PostgreSQL (chat persistence, audit logging)

### Tests

- `tests/test_query/` -- 15 test files

---

## app/redaction/

**Purpose**: Document redaction -- regex-based PII auto-detection, permanent PDF text removal (not visual masking), and immutable redaction audit logging.

### Files

| File | Description |
|------|-------------|
| `router.py` | POST /documents/{id}/redact, GET /documents/{id}/redaction-log, GET /documents/{id}/pii-detections |
| `service.py` | `RedactionService` -- PII detection, redaction application, audit log queries |
| `schemas.py` | RedactionType, PIICategory, PIIDetection, RedactionSpec, RedactRequest, RedactResponse, RedactionLogEntry |
| `engine.py` | `redact_pdf` -- pikepdf-based permanent text removal from PDF content streams, `hash_text` for audit |
| `pii_detector.py` | `detect_pii` -- regex patterns for SSN, phone, email, DOB + medical keyword detection |

### Key Schemas

- `RedactionType` -- StrEnum: pii, privilege, manual
- `PIICategory` -- StrEnum: ssn, phone, email, dob, medical
- `PIIDetection` -- text, category, confidence, start, end, chunk_index, page_number
- `RedactionSpec` -- page_number, start, end, reason, redaction_type, pii_category
- `RedactRequest` -- list of RedactionSpec (min 1)
- `RedactResponse` -- document_id, matter_id, redaction_count, redacted_pdf_path
- `RedactionLogEntry` -- immutable audit: id, document_id, user_id, redaction_type, reason, original_text_hash
- `RedactionLogResponse` -- paginated

### Endpoints

- `POST /api/v1/documents/{document_id}/redact` -- apply redactions to PDF (attorney/admin only, permanent removal)
- `GET /api/v1/documents/{document_id}/redaction-log` -- immutable redaction audit log
- `GET /api/v1/documents/{document_id}/pii-detections` -- auto-detect PII in document chunks

### Feature Flags

- `ENABLE_REDACTION` (default: `false`) -- gates redaction functionality

### Dependencies

- Uses: pikepdf (PDF manipulation), PostgreSQL (redaction_log table), MinIO (redacted PDF storage), Qdrant (fetch chunk texts for PII detection)

### Tests

- `tests/test_redaction/` -- 1 test file

---

## app/config.py

**Purpose**: Centralized configuration via Pydantic Settings. All configuration from environment variables / `.env` file.

### Key Feature Flags Summary

| Flag | Default | Controls |
|------|---------|----------|
| `ENABLE_VISUAL_EMBEDDINGS` | `false` | ColQwen2.5 visual embeddings |
| `ENABLE_RELATIONSHIP_EXTRACTION` | `false` | Instructor+LLM relationship extraction |
| `ENABLE_RERANKER` | `false` | bge-reranker-v2-m3 cross-encoder |
| `ENABLE_SPARSE_EMBEDDINGS` | `false` | FastEmbed BM42 sparse vectors + RRF |
| `ENABLE_EMAIL_THREADING` | `true` | RFC 5322 email thread detection |
| `ENABLE_NEAR_DUPLICATE_DETECTION` | `false` | MinHash+LSH dedup |
| `ENABLE_AI_AUDIT_LOGGING` | `true` | AI call audit trail |
| `ENABLE_BATCH_EMBEDDINGS` | `false` | Batch embedding API (stub) |
| `ENABLE_CASE_SETUP_AGENT` | `false` | LangGraph case setup pipeline |
| `ENABLE_COREFERENCE_RESOLUTION` | `false` | spaCy+coreferee pronoun resolution |
| `ENABLE_GRAPH_CENTRALITY` | `false` | Neo4j GDS centrality algorithms |
| `ENABLE_HOT_DOC_DETECTION` | `false` | Sentiment/hot doc scoring |
| `ENABLE_TOPIC_CLUSTERING` | `false` | BERTopic unsupervised clustering |
| `ENABLE_AGENTIC_PIPELINE` | `true` | Agentic vs. v1 fixed query graph |
| `ENABLE_CITATION_VERIFICATION` | `true` | CoVe claim verification |
| `ENABLE_REDACTION` | `false` | PDF redaction engine |

### Nested Config Groups

Settings exposes nested config objects via `@model_validator`:
- `settings.llm` -- `LLMConfig`
- `settings.embedding` -- `EmbeddingConfig`
- `settings.database` -- `DatabaseConfig`
- `settings.storage` -- `StorageConfig`
- `settings.retrieval` -- `RetrievalConfig`
- `settings.auth` -- `AuthConfig`
- `settings.processing` -- `ProcessingConfig`
- `settings.features` -- `FeatureFlags`

---

## app/dependencies.py

**Purpose**: FastAPI dependency injection -- singleton factory functions for all service clients.

### Key Factories

- `get_db()` -- async SQLAlchemy session
- `get_settings()` -- cached Settings instance
- `get_minio()` -- `StorageClient` singleton
- `get_qdrant()` -- `VectorStoreClient` singleton
- `get_graph_service()` -- `GraphService` (Neo4j) singleton
- `get_redis()` -- Redis client
- `get_llm()` -- `LLMClient` singleton
- `get_embedder()` -- `EmbeddingProvider` singleton (OpenAI or local)
- `get_retriever()` -- `HybridRetriever` singleton
- `get_query_graph()` -- compiled LangGraph query graph

---

## Test Coverage Summary

| Module | Test Files |
|--------|-----------|
| `tests/test_ingestion/` | 15 |
| `tests/test_query/` | 15 |
| `tests/test_common/` | 8 |
| `tests/test_entities/` | 7 |
| `tests/test_evaluation/` | 7 |
| `tests/test_analysis/` | 6 |
| `tests/test_analytics/` | 6 |
| `tests/test_cases/` | 5 |
| `tests/test_auth/` | 4 |
| `tests/test_documents/` | 4 |
| `tests/test_edrm/` | 4 |
| `tests/test_datasets/` | 2 |
| `tests/test_annotations/` | 1 |
| `tests/test_audit/` | 1 |
| `tests/test_exports/` | 1 |
| `tests/test_redaction/` | 1 |
| **Total** | **87** |

Additional test directories: `tests/test_e2e/`, `tests/test_integration/`, `tests/test_health.py`.
