# NEXUS platform: Epstein files ingestion and GCP architecture guide

**The HuggingFace dataset at `svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` contains 69,290 pre-computed 768-dimensional nomic-embed-text embeddings in Parquet format (357 MB), directly loadable into Qdrant in under two minutes — eliminating the need for re-embedding.** The dataset covers only the House Oversight Committee's November 2025 release (~20,000+ pages), not the massive DOJ EFTA corpus (3.5 million pages, 300+ GB). A companion dataset from the same creator covers FBI files with richer metadata. For production persistence on GCP, the optimal architecture replaces MinIO with GCS's S3-compatible API for document storage (~$1/month for 50 GB) while running Qdrant and Neo4j on persistent SSD disks (~$3.40/month combined), totaling roughly **$6/month** for all storage.

---

## The HuggingFace dataset: 69,290 chunks across four sparse columns

The dataset stores **69,290 embedding vectors in a single Parquet file (357 MB)** with a minimal four-column schema:

| Column | Type | Description |
|--------|------|-------------|
| `source_file` | string | Filename pattern: `{TYPE}-{NUM}-HOUSE_OVERSIGHT_{DOCNUM}.txt` |
| `chunk_index` | int64 | Position within document (range 0–1,340) |
| `text` | string | OCR'd chunk text (20–200 characters typical) |
| `embedding` | list\[float\] × 768 | nomic-embed-text vector |

**Critically, the schema lacks page numbers, Bates numbers, document IDs, and OCR confidence scores.** This is a retrieval-only dataset — adequate for semantic search but insufficient for citation-grade legal work without enrichment. The `source_file` field uses prefixes `IMAGES-` (OCR'd JPGs) and `TEXT-` (native text extractions), all referencing `HOUSE_OVERSIGHT_` document numbers.

The embedding model is **nomic-embed-text run via Ollama locally**, producing **768-dimensional vectors**. The exact version (v1 vs v1.5) is not specified in the dataset card — a production concern since query embeddings must use the identical model variant. The v1.5 model supports Matryoshka dimensionality (768→512→256) while v1 is fixed at 768. Both produce 768d by default, so pre-computed vectors work with either version for query encoding, but **v1.5 is the safer assumption** given the November 2025 creation date. Chunking parameters aren't documented for this dataset, but the creator's FBI files dataset uses **1,500 characters with 300-character overlap** — likely the same strategy here.

The dataset was exported on **November 21, 2025**, nine days after the House Oversight Committee released the source documents. It derives from `tensonaut/EPSTEIN_FILES_20K`, which contains 25,000+ plain text files OCR'd from the committee's release using **Tesseract**. The upstream dataset maintainer explicitly warns: *"There is ALOT of data. OCR made mistakes scanning the files...there is a lot of noise in the dataset, whether it be from OCR taking words out of normal 'pictures' from the pdf's, or character recognition failure."* Sample data confirms severe degradation on legal document headers (e.g., Bates stamps rendering as gibberish), while typed text and emails are reasonably clean.

**A significantly richer companion dataset exists**: `svetfm/epstein-fbi-files` (3.31 GB, 236,174 chunks from 8,150 FBI documents) includes Bates numbers, OCR confidence scores, page numbers, source volumes, and document types — all generated with **AWS Textract** rather than Tesseract. For production legal RAG, this FBI dataset is architecturally superior despite covering different source material.

---

## Source document landscape: 300+ GB across four major releases

The Epstein document universe spans four primary sources of vastly different scale:

**DOJ Epstein Files Transparency Act (EFTA) release — Datasets 1–12** dominates at **~305–400 GB compressed**, containing approximately **3.5 million released pages** (from 6 million identified). This is the motherlode. The DOJ removed bulk ZIP downloads on February 6, 2026, making **torrents the only reliable bulk acquisition method** — verified magnet links with SHA hashes are maintained at `github.com/yung-megafone/Epstein-Files`. Internet Archive mirrors exist for most datasets. Dataset 9 (~180 GB of emails and internal DOJ correspondence) remains incomplete — the DOJ's server cuts off at ~49 GB, and community archivists have recovered only ~96 GB via brute-force individual file downloads, with three large video files (~11 GB) unrecoverable.

| DOJ Dataset | Size | Contents | Status |
|-------------|------|----------|--------|
| 1–7 | ~4.2 GB combined | FBI interviews, police reports (2005–2008) | ✅ Complete |
| 8 | ~10.7 GB | FBI interviews, police reports | ✅ Complete |
| 9 | ~180 GB (49–96 GB recovered) | Emails, DOJ correspondence re: 2008 NPA | ⚠️ Incomplete |
| 10 | ~82 GB | 180,000 images + 2,000 videos from properties | ✅ Complete |
| 11 | ~27.5 GB | Financial ledgers, flight manifests, property records | ✅ Complete |
| 12 | ~114 MB | Late productions, supplemental items | ✅ Complete |

**House Oversight Committee releases (September–November 2025)** total **~53,000 pages**: 33,295 pages of DOJ records (September 8, 2025) plus 20,000+ pages of Epstein estate documents (November 12, 2025). The November batch — emails, JPG screenshots, contact records — is what the HuggingFace dataset covers. Originals were distributed via Google Drive in mixed formats (PDFs, ~23,124 JPGs, text files). The "House Post" in the dataset name refers specifically to this committee post/release.

**SDNY Giuffre v. Maxwell (Case 1:15-cv-07433-LAP)** unsealed documents released in **8+ batches starting January 3, 2024** comprise ~2,000–3,000 pages of motions, depositions, and exhibits. Free access is available through CourtListener's RECAP archive at `courtlistener.com/docket/4355835/giuffre-v-maxwell/`, Public Intelligence (batches 1–8), and consolidated PDFs from The Guardian and Newsweek.

**FBI FOIA Vault** (`vault.fbi.gov/jeffrey-epstein`) contains 22 parts totaling ~50–100 MB (~2,000–3,000 pages) of older pre-2025 FOIA releases — scanned image PDFs without OCR text layers.

**Pre-processed datasets ready for RAG ingestion** save significant processing time:

- `svetfm/epstein-fbi-files` — 3.31 GB, 236K chunks with Textract OCR + 768d embeddings (production-ready)
- `tensonaut/EPSTEIN_FILES_20K` — 106 MB CSV, 25K+ text files with Tesseract OCR
- `to-be/epstein-emails` — 3,997 emails extracted via Qwen 2.5 VL 72B vision model
- `notesbymuneeb/epstein-emails` — 5,082 email threads (16,447 messages) parsed via xAI Grok
- Zenodo record 18512562 — PDFs, images, text, and web sources from November 2025

The community site `epstein-files.org` (Sifter Labs) has processed **106,000+ files (188 GB)** into a searchable database using hybrid vector + keyword search (60/40 split with pgvector), representing the most complete indexed collection.

---

## Loading pre-computed embeddings directly into Qdrant

**Yes, the pre-computed 768d embeddings load directly into Qdrant from Parquet with zero re-embedding.** The workflow is straightforward:

```python
from datasets import load_dataset
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

client = QdrantClient(host="localhost", port=6333)
dataset = load_dataset("svetfm/epstein-files-nov11-25-house-post-ocr-embeddings")

# Create collection
client.create_collection(
    collection_name="epstein_house",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
)

# Batch upload — completes in under 2 minutes for 69K points
points = [
    PointStruct(
        id=i,
        vector=item["embedding"],
        payload={"text": item["text"], "source_file": item["source_file"],
                 "chunk_index": item["chunk_index"]}
    )
    for i, item in enumerate(dataset["train"])
]
client.upload_points("epstein_house", points=points, batch_size=1000, parallel=4)
```

**The critical constraint**: all query embeddings must be generated with the same nomic-embed-text model. Mixing embedding models (e.g., querying with MiniLM against nomic vectors) produces meaningless similarity scores — they occupy incompatible vector spaces. For the NEXUS app, this means running nomic-embed-text locally via Ollama, sentence-transformers, or FastEmbed (Qdrant's ONNX-optimized library that natively supports nomic-embed-text) for query encoding.

At **69,290 vectors × 768 dimensions**, Qdrant will consume approximately **~250–400 MB of RAM** with overhead — trivially small. Search latency at this scale is **under 5ms at p50**. Qdrant benchmarked 4.74ms p50 on a 50-million-vector × 768d collection, so 69K vectors will respond near-instantaneously.

---

## GCP storage architecture: replace MinIO with GCS, databases on persistent SSD

**MinIO's GCS gateway was deprecated and removed in June 2022**, eliminating the option of using GCS as a MinIO backend. Two viable paths remain for the NEXUS platform:

**Option A (recommended for simplicity): Replace MinIO with GCS's S3-compatible XML API.** GCS supports HMAC-authenticated S3 operations via `https://storage.googleapis.com` as the endpoint. The code change is minimal — swap the endpoint URL and credentials in your boto3 client. One critical caveat: recent AWS SDK versions added default checksum validation that breaks GCS compatibility; set `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` and `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` as environment variables.

```python
# Replace MinIO with GCS — single config change
s3_client = boto3.client("s3",
    endpoint_url="https://storage.googleapis.com",
    region_name="auto",
    aws_access_key_id="GOOG_HMAC_ACCESS_KEY",
    aws_secret_access_key="GOOG_HMAC_SECRET_KEY")
```

**Option B: Run MinIO server on a persistent disk** if the NEXUS app uses advanced S3 features (bucket notifications, Select API, object locking) that GCS's S3 API doesn't fully support. For basic PUT/GET/LIST/DELETE operations, Option A is sufficient and eliminates infrastructure management.

**Qdrant requires block storage — it cannot run on GCS/S3.** The official Qdrant guidance states: *"Qdrant needs block level storage. It is a database/search engine and so it needs sufficient control over what is on disk."* The correct architecture mounts a **persistent SSD disk** to the Qdrant Docker container:

```bash
# Create and attach persistent SSD
gcloud compute disks create qdrant-data --size=10GB --type=pd-ssd --zone=us-central1-a
# Mount at /mnt/qdrant-ssd, then in docker-compose:
# volumes: - /mnt/qdrant-ssd:/qdrant/storage
```

Persistent disks **survive VM deletion** when configured independently — they are not tied to instance lifecycle. The same applies to Neo4j's data directory on a separate persistent SSD.

For **backups**, use GCP persistent disk snapshots (incremental, ~$0.026/GB/month) on a daily cron rather than Qdrant's native S3 snapshot feature, which has a known compatibility issue (#4705) with GCS returning 411 errors on multipart uploads.

### Monthly cost breakdown

| Component | Storage type | Size | Rate/GB/mo | Monthly cost |
|-----------|-------------|------|------------|-------------|
| Raw PDFs | GCS Standard | 50 GB | $0.020 | **$1.00** |
| Qdrant vectors | pd-ssd | 10 GB | $0.170 | **$1.70** |
| Neo4j graph | pd-ssd | 10 GB | $0.170 | **$1.70** |
| PD snapshots (backup) | Snapshot storage | ~20 GB | $0.026 | **$0.52** |
| GCS ops + egress | — | Minimal | — | **~$0.61** |
| **Total** | | | | **~$5.53/month** |

Intra-region network traffic between VMs and GCS in the same region is **free**. This architecture stores 70 GB of production data with full backup coverage for under $6/month.

---

## Re-embedding fallback: under two hours on CPU, or $3–5 via OpenAI

If the pre-computed embeddings can't be used (wrong model version, quality concerns requiring re-chunking, or switching embedding models), re-embedding the full corpus is fast and cheap:

**CPU performance for nomic-embed-text on GCP n2-standard-4 (4 vCPUs):**

| Runtime | Chunks/sec | Time for 150K chunks | Time for 75K chunks |
|---------|-----------|---------------------|---------------------|
| PyTorch (baseline) | 20–30 | 1.5–2 hours | 40–60 min |
| ONNX Runtime | 50–100 | 25–50 min | 12–25 min |
| ONNX + int8 quantization | 80–150 | **17–31 min** | **8–16 min** |

**ONNX Runtime delivers 2–5× speedup over PyTorch** on CPU with negligible quality loss. Qdrant's **FastEmbed library** wraps ONNX-optimized nomic-embed-text for CPU-first inference and is the recommended approach. With ONNX + int8 quantization, the entire 150K-chunk corpus embeds in **under 30 minutes** on a $0.13/hour n2-standard-4 instance — a one-time compute cost of roughly $0.07.

**Faster CPU alternatives with quality tradeoffs:**

- **BGE-small-en-v1.5** (33M params, 384d): 3–4× faster than nomic, MTEB retrieval score of ~51.8 vs nomic's ~49–50 — actually slightly *better* retrieval quality in a smaller, faster package
- **all-MiniLM-L6-v2** (22M params, 384d): 4–5× faster but **5–8% lower retrieval accuracy** — a meaningful gap for legal text where precision matters
- **BGE-base-en-v1.5** (110M params, 768d): Marginally faster than nomic with slightly better MTEB scores (63.55 vs 62.39)

For legal text specifically, **nomic-embed-text and BGE-base-en-v1.5 are the top open-source choices** at 768d. Both achieve ~84–86% top-5 retrieval accuracy on BEIR benchmarks.

**OpenAI Batch API** offers the fastest path with zero infrastructure:

| Model | Batch price | Cost (37.5M tokens) | Cost (75M tokens) |
|-------|-----------|--------------------|--------------------|
| text-embedding-3-large (3072d) | $0.065/1M | $2.44 | **$4.88** |
| text-embedding-3-small (1536d) | $0.01/1M | $0.38 | **$0.75** |

The Batch API completes within a **24-hour window** (often faster). At $3–5 for the entire corpus with text-embedding-3-large, OpenAI is the most cost-effective path to state-of-the-art embedding quality — but locks you into an external API dependency for query encoding.

---

## Conclusion: recommended ingestion strategy for NEXUS

**Use the pre-computed nomic embeddings immediately** — load the 357 MB Parquet file into Qdrant in minutes, then embed queries with nomic-embed-text via FastEmbed (ONNX) on CPU. This gets a functional semantic search running in under an hour with zero cost.

**For production enrichment**, prioritize `svetfm/epstein-fbi-files` (236K chunks with Bates numbers, page numbers, and OCR confidence from Textract) as the higher-quality dataset. The House Oversight dataset's Tesseract OCR quality is noticeably worse, and its sparse metadata limits citation capability.

**For full corpus coverage**, the DOJ EFTA Datasets 1–12 represent 3.5 million pages requiring bulk OCR — a project measured in weeks and terabytes, not hours. Start with the pre-processed HuggingFace datasets as an MVP, then expand incrementally. The torrent-based acquisition via `github.com/yung-megafone/Epstein-Files` is the only reliable bulk download method since the DOJ removed ZIP downloads in February 2026.

**The GCP architecture is straightforward and cheap**: GCS for documents (replacing MinIO), persistent SSDs for Qdrant and Neo4j, disk snapshots for backup — all under $6/month for 70 GB of data. The one architectural non-negotiable is that Qdrant must run on block storage, not object storage.