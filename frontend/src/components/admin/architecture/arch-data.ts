import type { Edge } from "@xyflow/react";
import { MarkerType } from "@xyflow/react";
import type { ArchNodeType, GroupNodeType, StorageNodeType, ExternalNodeType } from "./arch-nodes";

/* ------------------------------------------------------------------ */
/*  Layout constants                                                   */
/* ------------------------------------------------------------------ */

// Node sizing (approximate rendered sizes for layout math)
const NODE_W = 170;     // typical arch node width
const NODE_H = 70;      // typical arch node height (incl. tech label)
const STORAGE_W = 155;   // storage node width
const EXT_W = 200;       // external node width

// Spacing
const COL_GAP = 20;      // gap between columns within a group
const ROW_GAP = 16;      // gap between rows within a group
const GROUP_PAD_X = 24;  // horizontal padding inside group
const GROUP_PAD_TOP = 40; // top padding (room for label)
const GROUP_PAD_BOT = 20; // bottom padding
const SECTION_GAP = 40;   // vertical gap between groups

// Computed column positions for domain modules (4 columns)
const MOD_COL = (col: number) => GROUP_PAD_X + col * (NODE_W + COL_GAP);
// Domain module group width: 4 columns of nodes + gaps + padding
const MOD_GROUP_W = GROUP_PAD_X * 2 + 4 * NODE_W + 3 * COL_GAP;

// External services column (right side)
const EXT_X = MOD_GROUP_W + 60;

// Vertical positions for major sections
const Y_CLIENT = 0;
const CLIENT_H = GROUP_PAD_TOP + NODE_H + GROUP_PAD_BOT;

const Y_GATEWAY = Y_CLIENT + CLIENT_H + SECTION_GAP;
const GATEWAY_H = GROUP_PAD_TOP + NODE_H + 20 + GROUP_PAD_BOT; // +20 for middleware badges

const Y_MODULES = Y_GATEWAY + GATEWAY_H + SECTION_GAP;
const MOD_ROWS = 5; // max rows in any column
const MOD_GROUP_H = GROUP_PAD_TOP + MOD_ROWS * NODE_H + (MOD_ROWS - 1) * ROW_GAP + GROUP_PAD_BOT;

const Y_AGENTS = Y_MODULES + MOD_GROUP_H + SECTION_GAP;
const AGENT_ROWS = 2;
const AGENT_COLS = 3;
const AGENT_COL_W = NODE_W + 60; // agents have longer labels
const AGENTS_GROUP_W = GROUP_PAD_X * 2 + AGENT_COLS * AGENT_COL_W + (AGENT_COLS - 1) * COL_GAP;
const AGENTS_GROUP_H = GROUP_PAD_TOP + AGENT_ROWS * NODE_H + (AGENT_ROWS - 1) * ROW_GAP + GROUP_PAD_BOT;

const Y_STORAGE = Y_AGENTS + AGENTS_GROUP_H + SECTION_GAP;
const STORAGE_COLS = 3;
const STORAGE_ROWS = 2;
const STORAGE_COL_GAP = 30;
const STORAGE_GROUP_W = GROUP_PAD_X * 2 + STORAGE_COLS * STORAGE_W + (STORAGE_COLS - 1) * STORAGE_COL_GAP;
const STORAGE_GROUP_H = GROUP_PAD_TOP + STORAGE_ROWS * (NODE_H + 10) + (STORAGE_ROWS - 1) * ROW_GAP + GROUP_PAD_BOT;

// External services (right column, spanning from gateway to modules)
const EXT_GROUP_W = EXT_W + GROUP_PAD_X * 2;
const EXT_ITEMS = 5;
const EXT_ITEM_GAP = 18;
const EXT_GROUP_H = GROUP_PAD_TOP + EXT_ITEMS * (NODE_H + 10) + (EXT_ITEMS - 1) * EXT_ITEM_GAP + GROUP_PAD_BOT;

// Workers + Observability (right column, below external)
const Y_WORKERS = Y_AGENTS;
const WORKERS_GROUP_H = AGENTS_GROUP_H;

const Y_OBS = Y_STORAGE;
const OBS_GROUP_H = STORAGE_GROUP_H;

/* ------------------------------------------------------------------ */
/*  Group nodes                                                        */
/* ------------------------------------------------------------------ */

export const groupNodes: GroupNodeType[] = [
  {
    id: "g-client",
    type: "group",
    position: { x: (MOD_GROUP_W - 360) / 2, y: Y_CLIENT },
    style: { width: 360, height: CLIENT_H },
    data: { label: "Client Layer", color: "blue" },
  },
  {
    id: "g-gateway",
    type: "group",
    position: { x: (MOD_GROUP_W - 480) / 2, y: Y_GATEWAY },
    style: { width: 480, height: GATEWAY_H },
    data: { label: "API Gateway", color: "blue" },
  },
  {
    id: "g-modules",
    type: "group",
    position: { x: 0, y: Y_MODULES },
    style: { width: MOD_GROUP_W, height: MOD_GROUP_H },
    data: { label: "Domain Modules (20)", color: "violet" },
  },
  {
    id: "g-agents",
    type: "group",
    position: { x: 0, y: Y_AGENTS },
    style: { width: Math.max(MOD_GROUP_W, AGENTS_GROUP_W), height: AGENTS_GROUP_H },
    data: { label: "Agentic Layer — 6 LangGraph Agents + 17 Tools", color: "amber" },
  },
  {
    id: "g-external",
    type: "group",
    position: { x: EXT_X, y: Y_GATEWAY },
    style: { width: EXT_GROUP_W, height: EXT_GROUP_H },
    data: { label: "AI / ML Services", color: "amber" },
  },
  {
    id: "g-storage",
    type: "group",
    position: { x: 0, y: Y_STORAGE },
    style: { width: Math.max(MOD_GROUP_W, STORAGE_GROUP_W), height: STORAGE_GROUP_H },
    data: { label: "Data Layer", color: "emerald" },
  },
  {
    id: "g-workers",
    type: "group",
    position: { x: EXT_X, y: Y_WORKERS },
    style: { width: EXT_GROUP_W, height: WORKERS_GROUP_H },
    data: { label: "Background Workers", color: "rose" },
  },
  {
    id: "g-observability",
    type: "group",
    position: { x: EXT_X, y: Y_OBS },
    style: { width: EXT_GROUP_W, height: OBS_GROUP_H },
    data: { label: "Observability", color: "purple" },
  },
];

/* ------------------------------------------------------------------ */
/*  Client layer                                                       */
/* ------------------------------------------------------------------ */

export const clientNodes: ArchNodeType[] = [
  {
    id: "react-spa",
    type: "arch",
    position: { x: GROUP_PAD_X, y: GROUP_PAD_TOP },
    parentId: "g-client",
    extent: "parent" as const,
    data: {
      label: "React SPA",
      description: "React 19 · Vite · shadcn/ui",
      tech: "TanStack Router · orval · Zustand",
      icon: "globe",
      variant: "primary",
    },
  },
  {
    id: "vercel",
    type: "arch",
    position: { x: GROUP_PAD_X + NODE_W + COL_GAP, y: GROUP_PAD_TOP },
    parentId: "g-client",
    extent: "parent" as const,
    data: {
      label: "Vercel CDN",
      description: "Static hosting + /api/* proxy",
      icon: "cloud",
      variant: "default",
    },
  },
];

/* ------------------------------------------------------------------ */
/*  API Gateway                                                        */
/* ------------------------------------------------------------------ */

export const gatewayNodes: ArchNodeType[] = [
  {
    id: "fastapi",
    type: "arch",
    position: { x: GROUP_PAD_X, y: GROUP_PAD_TOP },
    parentId: "g-gateway",
    extent: "parent" as const,
    data: {
      label: "FastAPI",
      description: "uvicorn:8000 · OpenAPI · 23 DI factories",
      tech: "Pydantic v2 · SQLAlchemy · structlog",
      icon: "server",
      variant: "primary",
    },
  },
  {
    id: "middleware",
    type: "arch",
    position: { x: GROUP_PAD_X + NODE_W + 40, y: GROUP_PAD_TOP },
    parentId: "g-gateway",
    extent: "parent" as const,
    data: {
      label: "Middleware Chain",
      icon: "shield",
      variant: "primary",
      items: ["RequestID", "Logging", "Audit", "CORS", "JWT Auth"],
    },
  },
];

/* ------------------------------------------------------------------ */
/*  Domain modules — 4 columns                                         */
/* ------------------------------------------------------------------ */

function modNode(
  id: string,
  label: string,
  col: number,
  row: number,
  variant: "core" | "intelligence" | "workflow" | "management",
  description?: string,
  tech?: string,
): ArchNodeType {
  return {
    id,
    type: "arch",
    position: { x: MOD_COL(col), y: GROUP_PAD_TOP + row * (NODE_H + ROW_GAP) },
    parentId: "g-modules",
    extent: "parent" as const,
    data: { label, description, tech, variant },
  };
}

export const moduleNodes: ArchNodeType[] = [
  // Core (col 0)
  modNode("mod-query", "query", 0, 0, "core", "Agentic RAG pipeline", "LangGraph · Instructor"),
  modNode("mod-ingestion", "ingestion", 0, 1, "core", "6-entry, 8-stage pipeline", "Docling · Celery"),
  modNode("mod-documents", "documents", 0, 2, "core", "Metadata CRUD"),
  modNode("mod-entities", "entities", 0, 3, "core", "KG + NER", "GLiNER · Neo4j Driver"),
  // Intelligence (col 1)
  modNode("mod-cases", "cases", 1, 0, "intelligence", "Case Setup Agent", "LangGraph · Instructor"),
  modNode("mod-analytics", "analytics", 1, 1, "intelligence", "Comms matrix · centrality", "BERTopic"),
  modNode("mod-analysis", "analysis", 1, 2, "intelligence", "Sentiment · hot docs", "LangGraph"),
  modNode("mod-depositions", "depositions", 1, 3, "intelligence", "Witness profiling"),
  // Workflow (col 2)
  modNode("mod-annotations", "annotations", 2, 0, "workflow", "Highlights · tags"),
  modNode("mod-exports", "exports", 2, 1, "workflow", "CSV · JSON · EDRM"),
  modNode("mod-redaction", "redaction", 2, 2, "workflow", "PII · privilege"),
  modNode("mod-edrm", "edrm", 2, 3, "workflow", "Email threading"),
  modNode("mod-memos", "memos", 2, 4, "workflow", "Legal memos", "Instructor"),
  // Management (col 3)
  modNode("mod-auth", "auth", 3, 0, "management", "JWT · RBAC · SSO", "PyJWT · OIDC"),
  modNode("mod-flags", "feature_flags", 3, 1, "management", "48 flags · admin UI"),
  modNode("mod-llmconfig", "llm_config", 3, 2, "management", "Runtime providers"),
  modNode("mod-evaluation", "evaluation", 3, 3, "management", "QA datasets · runs"),
  modNode("mod-retention", "retention", 3, 4, "management", "Data lifecycle", "Celery"),
];

/* ------------------------------------------------------------------ */
/*  Agentic layer                                                      */
/* ------------------------------------------------------------------ */

function agentNode(id: string, label: string, col: number, row: number, description?: string, tech?: string): ArchNodeType {
  return {
    id,
    type: "arch",
    position: { x: GROUP_PAD_X + col * (AGENT_COL_W + COL_GAP), y: GROUP_PAD_TOP + row * (NODE_H + ROW_GAP) },
    parentId: "g-agents",
    extent: "parent" as const,
    data: { label, description, tech, variant: "agent", icon: "bot" },
  };
}

export const agentNodes: ArchNodeType[] = [
  agentNode("agent-investigation", "Investigation Agent", 0, 0, "create_react_agent · 17 tools", "LangGraph"),
  agentNode("agent-citation", "Citation Verifier", 1, 0, "CoVe · faithfulness scoring", "LangGraph"),
  agentNode("agent-case", "Case Setup Agent", 2, 0, "Claims · parties · terms", "LangGraph · Instructor"),
  agentNode("agent-hotdoc", "Hot Doc Scanner", 0, 1, "Risk scoring · 7 dimensions", "LangGraph"),
  agentNode("agent-completeness", "Contextual Completeness", 1, 1, "Gap detection · attachments", "LangGraph"),
  agentNode("agent-entity-res", "Entity Resolution", 2, 1, "Union-find · cosine dedup", "LangGraph"),
];

/* ------------------------------------------------------------------ */
/*  AI / ML external services                                          */
/* ------------------------------------------------------------------ */

const extY = (row: number) => GROUP_PAD_TOP + row * (NODE_H + 10 + EXT_ITEM_GAP);

export const externalNodes: ExternalNodeType[] = [
  {
    id: "ext-llm",
    type: "external",
    position: { x: GROUP_PAD_X, y: extY(0) },
    parentId: "g-external",
    extent: "parent" as const,
    data: {
      label: "LLM Providers",
      description: "Instructor · tenacity · structlog",
      icon: "brain",
      providers: ["Anthropic", "OpenAI", "Gemini", "vLLM", "Ollama"],
    },
  },
  {
    id: "ext-embed",
    type: "external",
    position: { x: GROUP_PAD_X, y: extY(1) },
    parentId: "g-external",
    extent: "parent" as const,
    data: {
      label: "Embedding Providers",
      description: "FastEmbed (sparse) · sentence-transformers",
      icon: "cpu",
      providers: ["OpenAI", "Ollama", "local", "Gemini", "TEI", "BGE-M3"],
    },
  },
  {
    id: "ext-ner",
    type: "external",
    position: { x: GROUP_PAD_X, y: extY(2) },
    parentId: "g-external",
    extent: "parent" as const,
    data: {
      label: "GLiNER NER",
      description: "CPU · ~50ms/chunk · gliner_multi_pii-v1",
      icon: "cpu",
    },
  },
  {
    id: "ext-reranker",
    type: "external",
    position: { x: GROUP_PAD_X, y: extY(3) },
    parentId: "g-external",
    extent: "parent" as const,
    data: {
      label: "Reranker",
      description: "bge-reranker-v2-m3 · MPS/CUDA/CPU",
      icon: "cpu",
    },
  },
  {
    id: "ext-bertopic",
    type: "external",
    position: { x: GROUP_PAD_X, y: extY(4) },
    parentId: "g-external",
    extent: "parent" as const,
    data: {
      label: "BERTopic",
      description: "Topic clustering · feature-flagged",
      icon: "cpu",
    },
  },
];

/* ------------------------------------------------------------------ */
/*  Data layer (storage nodes) — 2 rows x 3 columns                   */
/* ------------------------------------------------------------------ */

function storageNode(
  id: string,
  label: string,
  tech: string,
  description: string,
  col: number,
  row: number,
  icon?: string,
): StorageNodeType {
  return {
    id,
    type: "storage",
    position: {
      x: GROUP_PAD_X + col * (STORAGE_W + STORAGE_COL_GAP),
      y: GROUP_PAD_TOP + row * (NODE_H + 10 + ROW_GAP),
    },
    parentId: "g-storage",
    extent: "parent" as const,
    data: { label, tech, description, icon },
  };
}

export const storageNodes: StorageNodeType[] = [
  // Row 0
  storageNode("st-postgres", "PostgreSQL", "v16 · SQLAlchemy · Alembic", "36 tables · users · audit · chat", 0, 0, "database"),
  storageNode("st-qdrant", "Qdrant", "v1.17 · qdrant-client", "Dense+sparse RRF · visual", 1, 0, "database"),
  storageNode("st-neo4j", "Neo4j", "v5 · neo4j-driver", "Entities · relationships · paths", 2, 0, "database"),
  // Row 1
  storageNode("st-minio", "MinIO", "S3 · boto3", "Raw files · parsed · pages", 0, 1, "drive"),
  storageNode("st-redis", "Redis", "v7 · aioredis", "Rate limit · cache · results", 1, 1, "database"),
  storageNode("st-rabbitmq", "RabbitMQ", "v3 · Celery", "Durable queues · dead-letter", 2, 1, "box"),
];

/* ------------------------------------------------------------------ */
/*  Background workers                                                 */
/* ------------------------------------------------------------------ */

export const workerNodes: ArchNodeType[] = [
  {
    id: "celery",
    type: "arch",
    position: { x: GROUP_PAD_X, y: GROUP_PAD_TOP },
    parentId: "g-workers",
    extent: "parent" as const,
    data: {
      label: "Celery Worker",
      description: "Autoscale 1–4",
      tech: "Celery · RabbitMQ/Redis",
      icon: "workflow",
      variant: "default",
      items: ["ingestion", "NER", "entity-res", "hot-doc", "retention"],
    },
  },
];

/* ------------------------------------------------------------------ */
/*  Observability                                                      */
/* ------------------------------------------------------------------ */

export const observabilityNodes: ArchNodeType[] = [
  {
    id: "obs-langsmith",
    type: "arch",
    position: { x: GROUP_PAD_X, y: GROUP_PAD_TOP },
    parentId: "g-observability",
    extent: "parent" as const,
    data: {
      label: "LangSmith",
      description: "Trace all LangGraph runs · nexus project",
      tech: "LangSmith SDK",
      icon: "eye",
      variant: "default",
    },
  },
  {
    id: "obs-audit",
    type: "arch",
    position: { x: GROUP_PAD_X, y: GROUP_PAD_TOP + NODE_H + 10 + ROW_GAP },
    parentId: "g-observability",
    extent: "parent" as const,
    data: {
      label: "Audit Logging",
      description: "audit_log · ai_audit_log",
      tech: "structlog · contextvars",
      icon: "eye",
      variant: "default",
    },
  },
];

/* ------------------------------------------------------------------ */
/*  All nodes combined                                                 */
/* ------------------------------------------------------------------ */

export const allNodes = [
  ...groupNodes,
  ...clientNodes,
  ...gatewayNodes,
  ...moduleNodes,
  ...agentNodes,
  ...externalNodes,
  ...storageNodes,
  ...workerNodes,
  ...observabilityNodes,
];

/* ------------------------------------------------------------------ */
/*  Edge styles                                                        */
/* ------------------------------------------------------------------ */

const requestFlow = {
  style: { stroke: "#3b82f6", strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6", width: 14, height: 14 },
};

const dataWrite = {
  style: { stroke: "#10b981", strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#10b981", width: 14, height: 14 },
};

const aiCall = {
  style: { stroke: "#f59e0b", strokeWidth: 1.5, strokeDasharray: "6 3" },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#f59e0b", width: 14, height: 14 },
};

const asyncDispatch = {
  style: { stroke: "#6b7280", strokeWidth: 1.5 },
  animated: true,
  markerEnd: { type: MarkerType.ArrowClosed, color: "#6b7280", width: 14, height: 14 },
};

const observability = {
  style: { stroke: "#a855f7", strokeWidth: 1, strokeDasharray: "3 3" },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#a855f7", width: 12, height: 12 },
};

/* ------------------------------------------------------------------ */
/*  Edges                                                              */
/* ------------------------------------------------------------------ */

export const allEdges: Edge[] = [
  // Client → Gateway
  { id: "e-spa-vercel", source: "react-spa", target: "vercel", ...requestFlow },
  { id: "e-vercel-fastapi", source: "vercel", target: "fastapi", ...requestFlow },
  { id: "e-fastapi-mw", source: "fastapi", target: "middleware", ...requestFlow },

  // Gateway → Domain Modules (core path)
  { id: "e-mw-query", source: "middleware", target: "mod-query", ...requestFlow },
  { id: "e-mw-ingestion", source: "middleware", target: "mod-ingestion", ...requestFlow },
  { id: "e-mw-documents", source: "middleware", target: "mod-documents", ...requestFlow },
  { id: "e-mw-entities", source: "middleware", target: "mod-entities", ...requestFlow },
  { id: "e-mw-cases", source: "middleware", target: "mod-cases", ...requestFlow },
  { id: "e-mw-analytics", source: "middleware", target: "mod-analytics", ...requestFlow },
  { id: "e-mw-auth", source: "middleware", target: "mod-auth", ...requestFlow },

  // Query module → Agents
  { id: "e-query-investigation", source: "mod-query", target: "agent-investigation", ...requestFlow },
  { id: "e-query-citation", source: "mod-query", target: "agent-citation", ...requestFlow },
  { id: "e-cases-agent", source: "mod-cases", target: "agent-case", ...requestFlow },
  { id: "e-analysis-hotdoc", source: "mod-analysis", target: "agent-hotdoc", ...asyncDispatch },
  { id: "e-entities-eres", source: "mod-entities", target: "agent-entity-res", ...asyncDispatch },
  { id: "e-analysis-completeness", source: "mod-analysis", target: "agent-completeness", ...asyncDispatch },

  // Modules → External AI services
  { id: "e-query-llm", source: "mod-query", target: "ext-llm", sourceHandle: "right", ...aiCall },
  { id: "e-cases-llm", source: "mod-cases", target: "ext-llm", sourceHandle: "right", ...aiCall },
  { id: "e-ingestion-embed", source: "mod-ingestion", target: "ext-embed", sourceHandle: "right", ...aiCall },
  { id: "e-entities-ner", source: "mod-entities", target: "ext-ner", sourceHandle: "right", ...aiCall },
  { id: "e-query-reranker", source: "mod-query", target: "ext-reranker", sourceHandle: "right", ...aiCall },
  { id: "e-analytics-bertopic", source: "mod-analytics", target: "ext-bertopic", sourceHandle: "right", ...aiCall },

  // Agents → External AI services
  { id: "e-investigation-llm", source: "agent-investigation", target: "ext-llm", sourceHandle: "right", ...aiCall },

  // Modules → Storage (data writes)
  { id: "e-query-pg", source: "mod-query", target: "st-postgres", ...dataWrite },
  { id: "e-query-qdrant", source: "mod-query", target: "st-qdrant", ...dataWrite },
  { id: "e-query-neo4j", source: "mod-query", target: "st-neo4j", ...dataWrite },
  { id: "e-ingestion-pg", source: "mod-ingestion", target: "st-postgres", ...dataWrite },
  { id: "e-ingestion-qdrant", source: "mod-ingestion", target: "st-qdrant", ...dataWrite },
  { id: "e-ingestion-minio", source: "mod-ingestion", target: "st-minio", ...dataWrite },
  { id: "e-entities-neo4j", source: "mod-entities", target: "st-neo4j", ...dataWrite },
  { id: "e-auth-pg", source: "mod-auth", target: "st-postgres", ...dataWrite },

  // Agents → Storage
  { id: "e-investigation-qdrant", source: "agent-investigation", target: "st-qdrant", ...dataWrite },
  { id: "e-investigation-neo4j", source: "agent-investigation", target: "st-neo4j", ...dataWrite },
  { id: "e-eres-neo4j", source: "agent-entity-res", target: "st-neo4j", ...dataWrite },

  // Celery async dispatch
  { id: "e-ingestion-celery", source: "mod-ingestion", target: "celery", sourceHandle: "right", ...asyncDispatch },
  { id: "e-celery-rabbitmq", source: "celery", target: "st-rabbitmq", ...asyncDispatch },
  { id: "e-celery-redis", source: "celery", target: "st-redis", ...asyncDispatch },

  // Middleware → Redis (rate limiting)
  { id: "e-mw-redis", source: "middleware", target: "st-redis", sourceHandle: "right", ...dataWrite },

  // LangGraph → PostgreSQL (checkpointer)
  { id: "e-investigation-pg", source: "agent-investigation", target: "st-postgres", ...dataWrite },

  // Observability edges
  { id: "e-query-langsmith", source: "mod-query", target: "obs-langsmith", sourceHandle: "right", ...observability },
  { id: "e-mw-audit", source: "middleware", target: "obs-audit", sourceHandle: "right", ...observability },
  { id: "e-audit-pg", source: "obs-audit", target: "st-postgres", targetHandle: "left", ...observability },
];
