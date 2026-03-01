# NEXUS — Feature Overview

> Multimodal RAG investigation platform for legal document intelligence.
> Ingests, analyzes, and queries 50,000+ page productions of mixed-format legal documents.

---

## What It Does

Upload your case documents (PDFs, emails, spreadsheets, presentations — any format). NEXUS automatically parses, indexes, and builds a knowledge graph across the entire corpus. Then ask questions in plain English and get cited, verifiable answers grounded in the actual evidence.

---

## Live Today

| Category | Features |
|---|---|
| **Document Ingestion** | Single/batch/ZIP upload. Supports PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT. Automatic parsing, chunking, embedding, entity extraction, and indexing. |
| **AI-Powered Q&A** | Natural language queries across the full corpus. Streaming answers with sources shown first. Persistent chat threads. Hybrid retrieval (semantic + keyword + knowledge graph). |
| **Entity & Relationship Graph** | Automatic extraction of people, orgs, dates. Deduplication of name variants (J. Smith = John Smith). Browse entities, connections, and document mentions. |
| **Security** | JWT login, 4 roles (admin, attorney, paralegal, reviewer). Case-scoped data isolation — users only see their assigned matters. |
| **Privilege Protection** | Tag documents as privileged/work-product/confidential. Enforced at the database level across all three stores (SQL, vector, graph) — not just UI filtering. |
| **Audit Trail** | Every API call logged: who, what, when, from where. Admin-only audit log viewer. |

---

## Coming Soon

### Case Intelligence
- **Case Setup Wizard** — Upload a Complaint; AI extracts claims, parties, defined terms, and a preliminary timeline. Lawyer reviews and confirms.
- **Persistent Context** — "Claim A", "the Company", "Defendant B" auto-resolve in every query without re-explanation.
- **Investigation Sessions** — Findings accumulate across a chain of queries.

### Smart Query Routing
- Simple lookups: **2-3 seconds**
- Multi-source questions: **5-8 seconds**
- Deep analytical queries: **15-30 seconds** (streaming)
- Two response modes: **narrative answers** (with inline citations) or **browsable result sets** (filterable, sortable, exportable document lists)

### Citation Verification
- Every factual claim independently verified by a second AI agent before display.
- Guards against hallucination and post-rationalization (model making up plausible-sounding citations).
- Target: **95%+ faithfulness**, **<5% hallucination rate**, **90%+ citation accuracy**.

### Sentiment & Hot Document Detection
- 7-dimension sentiment scoring per document (pressure, concealment, intent, etc.).
- Automatic flagging of admissions, guilt signals, deliberate vagueness.
- Context gap analysis: finds emails referencing missing attachments or undocumented conversations.

### Communication Analytics
- Sender-recipient volume matrix (interactive heatmap).
- Network centrality rankings (information brokers, influence, activity).
- Org hierarchy inference from email patterns (editable by lawyer).
- Automatic topic clustering of result sets.

### Email Intelligence
- Thread reconstruction from email headers.
- Inclusive email detection (most complete version of each thread).
- Near-duplicate detection and document version tracking.
- EDRM/Concordance/Relativity import and export.

### Modern Web Frontend (React)
- PDF viewer with annotation overlays
- Case setup wizard
- Defined terms sidebar (auto-populated glossary)
- Result set browser with dedup, sentiment, and pagination
- Communication matrix heatmap
- Network graph visualization
- Timeline view
- Hot document queue
- Org chart editor

### Annotations, Export & Redaction
- Highlight and annotate on PDF pages.
- Court-ready export: production packages, privilege logs, citation indices.
- EDRM-compliant export for Relativity/DISCO.
- Permanent redaction engine with PII/PHI auto-detection and audit log.

### Full Local Deployment
- Zero cloud dependency option — self-hosted LLM, embeddings, and reranker for maximum privilege protection.

---

## 10 Target Query Patterns

| # | Query Type | Example |
|---|---|---|
| Q1 | Document summary | "Summarize the Complaint and list all causes of action" |
| Q2 | Evidence reasoning | "Which documents are responsive to Claim A?" |
| Q3 | Key players & terms | "Who are the key players? What do the defined terms mean?" |
| Q4 | Multi-hop relationships | "Who participated in the Board meeting about the merger?" |
| Q5 | Org hierarchy + topics | "Show me reporting chains and top discussion topics per person" |
| Q6 | Deduplicated email sets | "All unique emails between Smith and Jones re: the contract" |
| Q7 | Missing context | "Emails referencing conversations not in the corpus" |
| Q8 | Admission detection | "Find documents with admission or guilt signals" |
| Q9 | Temporal + topics | "Timeline of all comms about Topic X, grouped by subject" |
| Q10 | Communication matrix | "Full sender-recipient volume grid for all custodians" |

---

## How It's Different From Generic AI Chat

| Generic RAG Chatbot | NEXUS |
|---|---|
| Stateless — every question is isolated | Persistent case context, investigation sessions |
| Flat document search | Knowledge graph with entity resolution across 50K+ pages |
| No citation verification | Independent verification agent checks every claim |
| No privilege awareness | Three-layer privilege enforcement (SQL + vector + graph) |
| No audit trail | Full SOC 2-ready audit logging |
| Single response format | Narrative answers OR browsable result sets, depending on query type |
| Text only | Multi-format: PDF, email, spreadsheets, presentations, images |
| Cloud-only | Optional fully local deployment for privilege protection |

---

## Tech Stack (Summary)

- **AI**: Claude Sonnet 4.5, OpenAI embeddings (swappable to local), GLiNER NER
- **Search**: Qdrant vector DB with hybrid dense+sparse retrieval, cross-encoder reranking
- **Graph**: Neo4j knowledge graph for entity relationships and multi-hop queries
- **Orchestration**: LangGraph agentic pipelines (6 autonomous agents)
- **API**: FastAPI with JWT auth, RBAC, rate limiting
- **Storage**: PostgreSQL (metadata), MinIO/S3 (documents), Redis (cache)
- **Processing**: Celery workers, Docling document parser

---

*Generated 2026-03-01*
