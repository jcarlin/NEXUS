import { PipelineNode, Arrow } from "./pipeline-node";
import { FlagBadge } from "./flag-badge";

interface IngestionPipelineProps {
  flagMap: Map<string, boolean>;
  embeddingInfo: { provider: string; model: string; dimensions: number } | null;
  settings: Map<string, string | number>;
  onToggleFlag?: (flagName: string, newValue: boolean) => void;
}

export function IngestionPipeline({ flagMap, embeddingInfo, settings, onToggleFlag }: IngestionPipelineProps) {
  const flag = (name: string) => flagMap.get(name) ?? false;
  const setting = (name: string) => settings.get(name);
  const fb = (name: string, label?: string) => ({
    name, enabled: flag(name), label, onToggle: onToggleFlag,
  });

  const chunkSize = setting("chunk_size") ?? 512;
  const chunkOverlap = setting("chunk_overlap") ?? 64;

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center">

      {/* Two entry points */}
      <div className="grid w-full max-w-3xl grid-cols-2 gap-3">
        <PipelineNode title="Path A: File Upload" variant="primary">
          <code className="rounded bg-muted px-1 text-[11px]">POST /documents/ingest</code>
          <br />
          Celery: <code className="rounded bg-muted px-1 text-[11px]">process_document()</code>
          <br />
          Downloads from MinIO &rarr; Docling parse
        </PipelineNode>
        <div className="rounded-lg border border-amber-500/40 border-l-[3px] border-l-amber-500 bg-card p-4">
          <h3 className="mb-1.5 text-sm font-semibold">Path B: Bulk Import</h3>
          <div className="text-xs leading-relaxed text-muted-foreground">
            <code className="rounded bg-muted px-1 text-[11px]">POST /datasets/import</code>
            <br />
            Celery: <code className="rounded bg-muted px-1 text-[11px]">run_bulk_import()</code>
            <br />
            Pre-parsed text, skips parse stage
            <br />
            <span className="text-[10px]">
              Adapters: directory, edrm_xml, concordance_dat, huggingface_csv, epstein_emails, google_drive
            </span>
          </div>
        </div>
      </div>
      <Arrow />

      {/* Stage 1: Parse */}
      <PipelineNode title="Stage 1: Parse">
        <span className="font-medium text-foreground">Docling:</span> PDF, DOCX, XLSX, PPTX, HTML, images
        <br />
        <span className="font-medium text-foreground">Email:</span> EML (RFC 822), MSG (Outlook) + attachment extraction &rarr; child jobs
        <br />
        <span className="font-medium text-foreground">Other:</span> CSV/TSV (auto-dialect) &bull; RTF &bull; TXT
        <br />
        <span className="text-[10px]">Bulk import skips this stage (text already extracted)</span>
      </PipelineNode>
      <Arrow dim={!flag("enable_ocr_correction")} />

      {/* OCR Correction */}
      <PipelineNode
        title="OCR Correction"
        disabled={!flag("enable_ocr_correction")}
        flags={[{ name: "enable_ocr_correction", enabled: flag("enable_ocr_correction") }]}
      >
        Regex: ligatures, digit/letter confusion, legal terms
        <br />
        Optional LLM-assisted correction for high-value documents
      </PipelineNode>
      <Arrow />

      {/* Stage 2: Chunk */}
      <PipelineNode title="Stage 2: Chunk">
        Semantic boundaries with token limits
        <br />
        <code className="rounded bg-muted px-1 text-[11px]">CHUNK_SIZE={String(chunkSize)}</code>{" "}
        <code className="rounded bg-muted px-1 text-[11px]">CHUNK_OVERLAP={String(chunkOverlap)}</code>{" "}
        &bull; Tokenizer: tiktoken cl100k_base
        <br />
        Email-aware: splits body vs quoted reply &bull; Tables as atomic units
      </PipelineNode>
      <Arrow dim />

      {/* Optional chunk enrichments */}
      <div className="grid w-full max-w-3xl grid-cols-2 gap-3">
        <PipelineNode
          title="Chunk Quality Scoring"
          disabled={!flag("enable_chunk_quality_scoring")}
          flags={[{ name: "enable_chunk_quality_scoring", enabled: flag("enable_chunk_quality_scoring") }]}
        >
          Heuristic: coherence, density, completeness, length (~5ms/chunk)
        </PipelineNode>
        <PipelineNode
          title="Contextual Chunks"
          disabled={!flag("enable_contextual_chunks")}
          flags={[{ name: "enable_contextual_chunks", enabled: flag("enable_contextual_chunks") }]}
        >
          LLM-generated 1-sentence context prefix per chunk (batched)
        </PipelineNode>
      </div>
      <Arrow dim={!flag("enable_document_summarization") && !flag("enable_multi_representation")} />

      {/* Summarization */}
      <PipelineNode
        title="Summarization"
        disabled={!flag("enable_document_summarization") && !flag("enable_multi_representation")}
      >
        <span className="inline-flex items-center gap-1.5">
          Document summary: 2-3 sentences
          <FlagBadge {...fb("enable_document_summarization", "DOC")} />
        </span>
        <br />
        <span className="inline-flex items-center gap-1.5">
          Chunk summaries: 1 sentence each &rarr; summary vector for triple RRF
          <FlagBadge {...fb("enable_multi_representation", "MULTI-REPR")} />
        </span>
      </PipelineNode>
      <Arrow />

      {/* Stage 3: Embed (3 tracks) */}
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Stage 3: Embed</p>
      <div className="mt-2 grid w-full max-w-3xl grid-cols-3 gap-3">
        <PipelineNode title="Dense Embed">
          {embeddingInfo ? (
            <>
              <code className="rounded bg-muted px-1 text-[11px]">{embeddingInfo.provider}</code>
              <br />
              <code className="rounded bg-muted px-1 text-[11px]">{embeddingInfo.model}</code>
              <br />
              {embeddingInfo.dimensions} dimensions
            </>
          ) : "loading..."}
        </PipelineNode>
        <PipelineNode
          title="Sparse Embed"
          disabled={!flag("enable_sparse_embeddings")}
          flags={[{ name: "enable_sparse_embeddings", enabled: flag("enable_sparse_embeddings") }]}
        >
          FastEmbed BM42
          <br />
          <code className="rounded bg-muted px-1 text-[11px]">bm42-all-minilm</code>
          <br />
          Lexical weights
        </PipelineNode>
        <PipelineNode
          title="Visual Embed"
          disabled={!flag("enable_visual_embeddings")}
          flags={[{ name: "enable_visual_embeddings", enabled: flag("enable_visual_embeddings") }]}
        >
          ColQwen2.5
          <br />
          <code className="rounded bg-muted px-1 text-[11px]">colqwen2.5-v0.2</code>
          <br />
          128d/token &bull; Complex pages only
        </PipelineNode>
      </div>
      <Arrow />

      {/* Qdrant upsert */}
      <PipelineNode title="Qdrant Upsert" variant="store">
        <code className="rounded bg-muted px-1 text-[11px]">nexus_text</code>: named vectors{" "}
        <code className="rounded bg-muted px-1 text-[11px]">dense</code> +{" "}
        <code className="rounded bg-muted px-1 text-[11px]">sparse</code> (native RRF at query time)
        <br />
        <code className="rounded bg-muted px-1 text-[11px]">nexus_visual</code>: ColQwen2.5 multi-vector MaxSim (reranking only)
        <br />
        <span className="text-[10px]">Bulk import: HNSW disabled during insert (m=0) &rarr; rebuilt after (m=16, ef=200)</span>
      </PipelineNode>
      <Arrow />

      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Parallel with embedding</p>
      <Arrow />

      {/* Stage 4: Entity extraction */}
      <PipelineNode title="Stage 4: Entity Extraction">
        <span className="font-medium text-foreground">Tier 1 &mdash; GLiNER NER</span> (always on)
        <br />
        Model: <code className="rounded bg-muted px-1 text-[11px]">urchade/gliner_multi_pii-v1</code> &bull; Threshold: 0.3 &bull; CPU
        <br />
        Types: person, organization, location, date, monetary_amount, case_number, court, vehicle
        <br /><br />
        <span className="inline-flex items-center gap-1.5">
          <span className="font-medium text-foreground">Tier 2 &mdash; LLM Relationship Extraction</span>
          <FlagBadge {...fb("enable_relationship_extraction")} />
        </span>
        <br />
        Instructor + LLM for chunks with 2+ entities &rarr; RELATED_TO, REPORTS_TO edges
        <br />
        <span className="inline-flex items-center gap-1.5">
          Coreference resolution: pronoun &rarr; entity linking
          <FlagBadge {...fb("enable_coreference_resolution", "COREF")} />
        </span>
      </PipelineNode>
      <Arrow />

      {/* Neo4j */}
      <PipelineNode title="Neo4j Indexing" variant="store">
        <span className="font-medium text-foreground">Nodes:</span> :Document, :Entity (+ type label), :Chunk, :Email
        <br />
        <span className="font-medium text-foreground">Edges:</span> MENTIONED_IN, CONTAINS, SENT, SENT_TO, CC, BCC
        <br />
        <span className="font-medium text-foreground">Enriched:</span> RELATED_TO (Tier 2), REPORTS_TO (hierarchy)
      </PipelineNode>
      <Arrow />

      {/* Stage 5: Completion */}
      <PipelineNode title="Stage 5: Completion">
        <span className="font-medium text-foreground">Document record:</span> PostgreSQL upsert
        <br />
        <span className="inline-flex items-center gap-1.5">
          <span className="font-medium text-foreground">Email threading:</span> RFC 5322 Message-ID / In-Reply-To / References
          <FlagBadge {...fb("enable_email_threading")} />
        </span>
        <br />
        <span className="font-medium text-foreground">Communication pairs:</span> Analytics sender-recipient graph
        <br />
        <span className="inline-flex items-center gap-1.5">
          <span className="font-medium text-foreground">Near-duplicate:</span> MinHash + Jaccard &ge; 0.80
          <FlagBadge {...fb("enable_near_duplicate_detection", "DEDUP")} />
        </span>
        <br />
        <span className="inline-flex items-center gap-1.5">
          <span className="font-medium text-foreground">Hot doc scan:</span> 7 sentiment dims + 3 signals + anomaly
          <FlagBadge {...fb("enable_hot_doc_detection", "HOT DOC")} />
        </span>
        <br />
        <span className="font-medium text-foreground">Entity resolution:</span> Fuzzy match &ge; 90 + transitive merge
      </PipelineNode>
      <Arrow />

      {/* Output */}
      <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/5 px-5 py-2.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
        Document indexed &bull; Entities linked &bull; Ready for query
      </div>

      {/* Bulk import detail */}
      <div className="mt-10 w-full">
        <h3 className="mb-1 text-sm font-semibold">Bulk Import Orchestration</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Orchestrated by <code className="rounded bg-muted px-1 text-[11px]">run_bulk_import()</code> Celery task
        </p>
        <PipelineNode title="Dataset Adapters & Optimizations" className="max-w-none">
          <span className="font-medium text-foreground">6 Adapters:</span>
          <br />
          &bull; <code className="rounded bg-muted px-1 text-[11px]">directory</code> &mdash; Local filesystem
          <br />
          &bull; <code className="rounded bg-muted px-1 text-[11px]">edrm_xml</code> &mdash; EDRM XML load file
          <br />
          &bull; <code className="rounded bg-muted px-1 text-[11px]">concordance_dat</code> &mdash; Concordance DAT
          <br />
          &bull; <code className="rounded bg-muted px-1 text-[11px]">huggingface_csv</code> &mdash; HuggingFace dataset CSV
          <br />
          &bull; <code className="rounded bg-muted px-1 text-[11px]">epstein_emails</code> &mdash; FBI email corpus
          <br />
          <span className="inline-flex items-center gap-1.5">
            &bull; <code className="rounded bg-muted px-1 text-[11px]">google_drive</code> &mdash; OAuth connector
            <FlagBadge {...fb("enable_google_drive")} />
          </span>
          <br /><br />
          <span className="font-medium text-foreground">Optimizations:</span>
          <br />
          &bull; HNSW disabled during bulk (m=0) &rarr; rebuilt after (5-10x speedup)
          <br />
          &bull; Content-hash deduplication + resume support
          <br />
          &bull; Per-doc subtasks for parallel Celery workers
          <br /><br />
          <span className="font-medium text-foreground">Post-ingestion hooks:</span>
          <br />
          &bull; entities.resolve_entities &bull; ingestion.detect_inclusive_emails
          <br />
          &bull; agents.hot_document_scan &bull; agents.entity_resolution_agent
        </PipelineNode>
      </div>
    </div>
  );
}
