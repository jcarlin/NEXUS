# Vault AI Systems — Master Product Roadmap

**Version:** 5.1
**Date:** February 21, 2026
**Status:** Active
**Supersedes:** Product Blueprint v3.0 (October 23, 2025)

---

## Document Purpose

This roadmap captures the complete product vision for the Vault Cube, organized into shippable stages. Nothing has been removed from previous planning — every feature, endpoint, and epic is here, assigned to the stage where it belongs. Each stage builds on the last and produces a working, demonstrable product.

---

## Product Summary

The Vault Cube is a secure, air-gapped enterprise AI hardware appliance. It ships pre-configured with GPU hardware, a hardened OS, AI inference engine, and management tooling. Customers plug it into their internal network and run AI workloads with zero internet connectivity.

**Hardware:** 2× NVIDIA RTX 5090 FE (64GB total VRAM, 1 currently installed), AMD Threadripper PRO 7975WX, 256GB DDR5 ECC RAM, dual NVMe (OS + models), tower form factor.

**Price point:** $40,000–$60,000 per unit.

**Target markets:** Universities, law firms, healthcare organizations, government, financial services.

---

# STAGE 1: Foundation

**Goal:** Bootable, hardened system with AI inference working on real hardware.
**Audience:** Internal team only. Not customer-facing.
**Estimated effort:** 60–75 hours
**Target:** Complete before any customer-facing work begins.

## Epic 1: Golden Image Automation (from Blueprint v3.0)

Create a repeatable, automated pipeline for building the base OS image.

**Key tech:** Packer, Ansible, Ubuntu 24.04 LTS

| Task | Description | Effort | Requires GPU | Status |
|------|-------------|--------|--------------|--------|
| 1.1 | Dev environment setup: VirtualBox/UTM, Ubuntu ISO, test VM | 2 hrs | No | ✅ |
| 1.2 | Git repo structure: Packer, Ansible, scripts, docs folders | 1 hr | No | ✅ |
| 1.3 | Packer template: Base Ubuntu with automated install (cloud-init) | 4–6 hrs | No | ✅ |
| 1.4 | Ansible playbooks — base system: updates, packages, user setup | 4 hrs | No | ✅ |
| 1.5 | CIS Level 1 hardening: Ansible playbook for security benchmarks | 6 hrs | No | ✅ |
| 1.6 | Docker installation: Docker Engine, containerd, docker-compose | 3 hrs | No | ✅ |
| 1.7 | Python & ML tools: Python 3.11+, pip, virtualenv, core libraries | 3 hrs | No | ✅ |
| 1.8 | NVIDIA driver installation: GPU drivers, CUDA 12.x toolkit | 4 hrs | **Yes** | ✅ (Driver 570, CUDA 12.8, kernel 6.13) |
| 1.9 | NVIDIA Container Toolkit: Enable Docker GPU access | 2 hrs | **Yes** | ✅ |
| 1.10 | Integration testing: Build complete golden image on real hardware | 4–6 hrs | **Yes** | ✅ (GCP GPU test passed Feb 21, 2026) |

**Subtotal: 33–41 hours** (70% can start without GPU hardware)

## Epic 2: Pre-Installed AI Stack (from Blueprint v3.0)

Install and configure all AI frameworks required for LLM inference.

**Key tech:** PyTorch, vLLM, CUDA, Hugging Face Transformers

| Task | Description | Effort | Dependencies | Status |
|------|-------------|--------|--------------|--------|
| 2.1 | PyTorch 2.x with CUDA 12.x support, verify GPU access | 3 hrs | Task 1.8 | ✅ (PyTorch 2.10+cu128) |
| 2.2 | CUDA Toolkit & cuDNN: Install, verify compatibility | 4 hrs | Task 1.8 | ✅ (CUDA 12.8, cuDNN 9.7) |
| 2.3 | vLLM container setup: NGC container, configure for RTX 5090 (Blackwell), test replica mode | 6 hrs | Tasks 2.1, 2.2 | ✅ (vLLM 0.13.0 via NGC 26.01-py3) |
| 2.4 | Hugging Face Transformers: Library, tokenizers, model cache config | 2 hrs | Task 2.1 | |
| 2.5 | ONNX Runtime with GPU support | 2 hrs | Task 2.2 | |
| 2.6 | TensorRT for optimized inference | 3 hrs | Task 2.2 | |
| 2.7 | DeepSpeed for fine-tuning capabilities (installed, not configured) | 2 hrs | Task 2.1 | |
| 2.8 | Pre-load models: 32B-class production model (Qwen 2.5 32B AWQ) + 8B-class fast model | 4 hrs | Tasks 2.3, 2.4 | |
| 2.9 | Multi-GPU benchmarking: Test replica parallelism (4×1), tensor parallel (TP=2, TP=4), pipeline parallel. Document real throughput numbers per config. | 6 hrs | All above | |

**Subtotal: 32–35 hours** (all require GPU hardware)

## Stage 1 Decisions Required

- [ ] **Hardware ordered and delivery confirmed** — blocker for everything GPU-dependent
- [ ] **OS version locked:** Ubuntu 24.04 LTS (changed from 22.04 in v3.0)
- [x] **vLLM version pinned:** vLLM 0.13.x via NGC container (nvcr.io/nvidia/vllm-inference:26.01-py3)
- [ ] **Production model selected:** Qwen 2.5 32B AWQ recommended (Apache 2.0 license, fits single GPU for replica mode)
- [ ] **Model licensing reviewed by legal** for commercial redistribution in hardware product

## Stage 1 Exit Criteria

- [x] Packer + Ansible pipeline produces bootable, hardened Ubuntu image
- [x] All NVIDIA drivers, CUDA, and vLLM installed and functional (validated on GCP Feb 2026)
- [ ] vLLM serving inference on RTX 5090 in replica mode (pending Cube deployment)
- [ ] Multi-GPU benchmarks documented with real throughput numbers (pending second GPU install)
- [x] Golden image is reproducible — can be rebuilt from scratch in <1 hour

---

# STAGE 2: Rev 1 — Shippable Pilot Product

**Goal:** A product you can put in front of 1–3 pilot customers. Box boots, chat works, data is private.
**Audience:** Pilot customers (friendly university, law firm, or healthcare org).
**Estimated effort:** 120–160 hours (on top of Stage 1)
**Target:** 4–6 weeks after Stage 1 complete.

## Epic 3: API Gateway (Minimal) ✅

**3 endpoints.** Everything else is handled by existing tools.

**Key tech:** FastAPI, httpx, SQLite, uvicorn

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 3.1 | FastAPI project scaffold: app structure, config, Docker container | 4 hrs | ✅ |
| 3.2 | vLLM proxy client: async httpx client that forwards requests to vLLM, handles streaming SSE pass-through | 8 hrs | ✅ |
| 3.3 | `POST /v1/chat/completions` — inference endpoint with streaming support. Industry-standard LLM API format (OpenAI-compatible). | 6 hrs | ✅ |
| 3.4 | `GET /v1/models` — list available models from local manifest file | 2 hrs | ✅ |
| 3.5 | `GET /vault/health` — system health check (vLLM status, GPU detection) | 2 hrs | ✅ |
| 3.6 | API key auth middleware: validate Bearer tokens against hashed keys in SQLite | 4 hrs | ✅ |
| 3.7 | Request logging middleware: log every request (timestamp, user, endpoint, model, token count, latency) to structured log files + AuditLog DB table | 4 hrs | ✅ |
| 3.8 | Docker container + systemd service for gateway, auto-start on boot | 3 hrs | ✅ |
| 3.9 | Integration testing: end-to-end from API request → vLLM → streamed response | 4 hrs | ✅ |

**Subtotal: 37 hours**

### Rev 1 API Key Management (CLI Tool, Not API) ✅

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 3.10 | `vault-admin` CLI tool: `create-key`, `list-keys`, `revoke-key` commands. Writes to same SQLite database as auth middleware. | 6 hrs | ✅ |

### Rev 1 GPU & Model Configuration (Config Files, Not API) ✅

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 3.11 | GPU config file (`/opt/vault/config/gpu-config.yaml`): parallelism strategy, model assignment, memory utilization settings. vLLM reads on startup. | 3 hrs | ✅ |
| 3.12 | Model manifest file (`/opt/vault/config/models.json`): list of installed models with metadata (size, quantization, VRAM needed, description). API reads for `/v1/models`. | 2 hrs | ✅ |
| 3.13 | Service restart script: `vault-reload` command that safely restarts vLLM with new config | 2 hrs | ✅ |

## Epic 4: Chat UI ✅

The customer-facing interface. Must look like a $50K enterprise product, not a developer tool.

**Key tech:** React, TypeScript, Tailwind CSS (NOT Gradio, NOT Streamlit)

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 4.1 | React project scaffold with build pipeline, served via nginx or FastAPI static files | 4 hrs | ✅ |
| 4.2 | Chat interface: message input, streaming response display, conversation thread | 16 hrs | ✅ |
| 4.3 | Conversation management: create new, switch between, rename, delete. Stored in browser localStorage for Rev 1 (no server-side storage yet). | 8 hrs | ✅ |
| 4.4 | Model selector: dropdown showing available models from `/v1/models` | 3 hrs | ✅ |
| 4.5 | System prompt configuration: per-conversation custom instructions | 4 hrs | ✅ |
| 4.6 | Settings panel: API key entry, theme (light/dark), basic preferences | 4 hrs | ✅ |
| 4.7 | File upload UI: drag-and-drop for documents (basic file type validation — Stage 1 quarantine only) | 6 hrs | ✅ |
| 4.8 | System status indicator: green/yellow/red dot showing health from `/vault/health` | 2 hrs | ✅ |
| 4.9 | Responsive design: works on desktop and tablet (customers will use from workstations) | 4 hrs | ✅ |
| 4.10 | Branding and polish: Vault AI branding, professional typography, loading states, error handling | 6 hrs | ✅ |

**Subtotal: 57 hours**

## Epic 5: First-Boot Wizard ✅

Integrated into the main React app (not standalone). Runs before auth gate on first boot, then disables itself.

**Key tech:** React (shared app with chat UI), FastAPI backend for system config

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 5.1 | First-boot detection: systemd flag file, wizard app starts only if flag present | 2 hrs | ✅ (backend flag file + middleware gating) |
| 5.2 | Step 1 — Welcome & network: Confirm hostname, IP (DHCP or static), timezone | 4 hrs | ✅ |
| 5.3 | Step 2 — Admin account: Create admin credentials (Vault app admin + API key) | 3 hrs | ✅ |
| 5.4 | Step 3 — TLS certificate: Generate self-signed cert (custom upload deferred to Settings) | 6 hrs | ✅ |
| 5.5 | Step 4 — API key generation: Create first admin API key, display once with copy button | 3 hrs | ✅ |
| 5.6 | Step 5 — Model selection: Show pre-loaded models with descriptions, pick default | 4 hrs | ✅ |
| 5.7 | Step 6 — Verification: Run health checks (DB, inference, GPU, TLS), show results | 4 hrs | ✅ |
| 5.8 | Step 7 — Complete: Finalize setup, display API key, "Enter Vault" stores key and loads main app | 3 hrs | ✅ |
| 5.9 | Backend integration: 7 API endpoints with middleware gating, step tracking, system commands | 8 hrs | ✅ (7 endpoints, 19 tests) |

**Subtotal: 37 hours**

## Epic 6: Monitoring Setup (Pre-Configured, Not Custom-Built) ✅

Leverage Cockpit and Grafana — don't rebuild them.

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 6.1 | Cockpit installation and configuration: system admin, logs, services, terminal | 2 hrs | ✅ |
| 6.2 | Prometheus installation: node-exporter, nvidia-gpu-exporter, custom vLLM metrics exporter | 4 hrs | ✅ |
| 6.3 | Grafana installation with pre-built dashboards: GPU utilization, inference throughput/latency, system resources, disk space, temperatures | 8 hrs | ✅ |
| 6.4 | Landing page: `https://vault-cube.local` routes to chat UI, with links to Grafana (:3000) and Cockpit (:9090) for admins | 3 hrs | ✅ |
| 6.5 | Alert rules: Prometheus alerts for GPU temperature >80°C, disk >90% full, vLLM down, RAM >90% | 3 hrs | ✅ |

**Subtotal: 20 hours**

## Epic 7: Onboarding Agent (System Prompt) ✅

Nearly free if the chat UI and API are built. The AI introduces itself to first-time users.

| Task | Description | Effort |
|------|-------------|--------|
| 7.1 | ✅ Onboarding system prompt: Write and test the conversational onboarding flow (role detection, guided first task, feature tour, privacy explanation) | 4 hrs |
| 7.2 | ✅ First-time user detection: flag in localStorage, auto-inject onboarding system prompt for new users | 2 hrs |
| 7.3 | ✅ Onboarding completion: user can dismiss, system remembers and switches to standard assistant | 1 hr |

**Subtotal: 7 hours** ✅

## Rev 2 Frontend API Support (Pulled Forward from Stage 3) ✅

**28 additional endpoints** built to support the frontend UI, which was 100% mocked. These endpoints cover the subset of Stage 3's Epic 8 that the frontend actually uses. Heavy infra features (quarantine, updates, backup, LDAP) remain deferred. **134 tests total.**

**Model type/status:** `GET /v1/models` now returns `type` (chat/embedding) and `status` (running/available) fields. Embedding models auto-classified via family + name heuristics, running status fetched from Ollama `/api/ps`. Response sorted: running chat → available chat → running embedding → available embedding. Frontend filters embedding models from chat picker and defaults to the first running chat model.

| Area | Endpoints | Tests | Stage 3 Overlap |
|------|-----------|-------|-----------------|
| Conversations API | 6 (CRUD + messages) | 14 | Epic 8.3 ✅ |
| Training Jobs API | 7 (CRUD + lifecycle) | 10 | New (DB records only, no real training) |
| Admin API (users, keys, config) | 11 | 13 | Epic 8.5 partial ✅ |
| System/Insights/Activity | 4 | 10 | Epic 8.4 partial ✅ |

## Stage 2 Decisions Required

- [ ] **Pilot customers identified** (1–3, friendly contacts)
- [ ] **Form factor committed:** Tower workstation for Rev 1 (rackmount deferred)
- [ ] **Chat UI design direction** approved before development starts
- [ ] **Domain/hostname convention:** `vault-cube.local` or customer-chosen?
- [ ] **Support model:** Who handles pilot customer issues? (Likely CTO directly for Rev 1)

## Stage 2 Exit Criteria

- [ ] Customer plugs in Vault Cube, completes first-boot wizard in <10 minutes
- [ ] Chat UI works: users can converse with the AI, conversations persist locally
- [ ] API key authentication works end-to-end
- [ ] Any industry-standard LLM client (OpenAI SDK, curl, LangChain) can call the API by swapping base URL
- [x] Grafana shows GPU stats, inference metrics, system health
- [x] Cockpit available for admin system management
- [ ] At least 1 pilot customer has the unit deployed and providing feedback

## Stage 2 Total Effort: 120–160 hours

---

# STAGE 3: Rev 2 — Enterprise Features

**Goal:** Graduate from pilot to a product you can sell. Add the management, security, and operational features enterprise buyers require for procurement approval.
**Audience:** First paying customers. IT admins and security teams evaluating for purchase.
**Estimated effort:** 200–260 hours
**Target:** 8–12 weeks after Stage 2.

## Epic 8: Full API Gateway

Expand from 3 endpoints to the complete management API. Everything that was a CLI tool or config file in Rev 1 gets proper API endpoints.

### 8.1 Inference Endpoints (Expand from Rev 1) ✅

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| POST | `/v1/completions` | Legacy text completion proxy | 3 hrs | ✅ |
| POST | `/v1/embeddings` | Embedding generation (requires embedding model) | 4 hrs | ✅ |
| GET | `/v1/models/{model_id}` | Detailed model info: parameters, context window, VRAM, capabilities | 2 hrs | ✅ |

### 8.2 Model Management (Replace config files) ✅

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| GET | `/vault/models` | List all models on disk with status (loaded/available) | 3 hrs | ✅ |
| GET | `/vault/models/{model_id}` | Detailed model info | 2 hrs | ✅ |
| POST | `/vault/models/{model_id}/load` | Load model into GPU memory, handles vLLM restart gracefully | 8 hrs | ✅ |
| POST | `/vault/models/{model_id}/unload` | Unload model from GPU memory | 3 hrs | ✅ |
| GET | `/vault/models/active` | Currently loaded model(s) and GPU allocation | 2 hrs | ✅ |
| POST | `/vault/models/import` | Import model from USB/mounted drive with validation | 6 hrs | ✅ |
| DELETE | `/vault/models/{model_id}` | Delete model from disk (refuses if loaded) | 2 hrs | ✅ |

### 8.3 Conversations API (Replace localStorage) ✅ (pulled forward to Rev 2)

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| GET | `/vault/conversations` | List user's conversations, paginated | 3 hrs | ✅ |
| POST | `/vault/conversations` | Create conversation (title, system prompt, model) | 2 hrs | ✅ |
| GET | `/vault/conversations/{id}` | Full conversation with messages | 2 hrs | ✅ |
| PUT | `/vault/conversations/{id}` | Update metadata | 2 hrs | ✅ |
| DELETE | `/vault/conversations/{id}` | Delete conversation | 1 hr | ✅ |
| POST | `/vault/conversations/{id}/messages` | Add message, trigger inference | 3 hrs | ✅ |
| GET | `/vault/conversations/{id}/export` | Export as JSON or Markdown | 3 hrs | ✅ |

### 8.4 System Health & Monitoring (Supplement Grafana) ✅

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| GET | `/vault/system/health` | Expand: status of every service | 2 hrs | ✅ |
| GET | `/vault/system/gpu` | Per-GPU: utilization, VRAM, temp, power, fan speed | 3 hrs | ✅ |
| GET | `/vault/system/resources` | CPU, RAM, disk, uptime | 2 hrs | ✅ |
| GET | `/vault/system/inference` | Requests/min, avg latency, tokens/sec, queue depth | 3 hrs | ✅ |
| GET | `/vault/system/services` | Status of all managed services | 2 hrs | ✅ |
| POST | `/vault/system/services/{name}/restart` | Restart a service | 2 hrs | ✅ |
| GET | `/vault/system/logs` | Paginated logs, filterable by service/severity/time | 4 hrs | ✅ |
| `WS` | `/ws/system` | Live system metrics push for dashboard | 4 hrs | ✅ |

*Also added: `GET /vault/insights` (usage analytics) and `GET /vault/activity` (activity feed) in Rev 2.*

### 8.5 Administration (Replace CLI tools) ✅

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| GET | `/vault/admin/keys` | List API keys (prefix, label, scope, created — never full key) | 2 hrs | ✅ |
| POST | `/vault/admin/keys` | Generate new key (label, scope, rate limit, expiry) | 3 hrs | ✅ |
| PUT | `/vault/admin/keys/{key_id}` | Update key metadata | 2 hrs | ✅ |
| DELETE | `/vault/admin/keys/{key_id}` | Revoke key, immediately effective | 1 hr | ✅ |
| GET | `/vault/admin/audit` | Query audit log: filter by user, action, time, endpoint | 4 hrs | ✅ |
| GET | `/vault/admin/audit/export` | Export audit log as CSV/JSON for compliance | 3 hrs | ✅ |
| GET | `/vault/admin/audit/stats` | Aggregate: requests per user, tokens consumed, model usage | 3 hrs | ✅ |
| GET | `/vault/admin/config` | Current system configuration | 2 hrs | ✅ |
| PUT | `/vault/admin/config` | Update configuration (validates before applying) | 4 hrs | ✅ |
| GET | `/vault/admin/config/network` | Network settings | 1 hr | ✅ |
| PUT | `/vault/admin/config/network` | Update network config | 3 hrs | ✅ |
| GET | `/vault/admin/config/tls` | TLS certificate info | 1 hr | ✅ |
| POST | `/vault/admin/config/tls` | Upload custom TLS cert | 3 hrs | ✅ |

*Also added in Rev 2: user management (GET/POST/PUT/DELETE `/vault/admin/users`) and system settings (GET/PUT `/vault/admin/config/system`).*

### 8.6 First-Boot API (Replace standalone wizard) ✅

Move wizard backend into the API gateway for consistency.

| Method | Endpoint | Description | Effort | Status |
|--------|----------|-------------|--------|--------|
| GET | `/vault/setup/status` | Setup state: pending/in_progress/complete | 1 hr | ✅ |
| POST | `/vault/setup/network` | Configure hostname, IP | 2 hrs | ✅ |
| POST | `/vault/setup/admin` | Create admin account + first API key | 2 hrs | ✅ |
| POST | `/vault/setup/tls` | TLS mode selection | 2 hrs | ✅ |
| POST | `/vault/setup/model` | Select default model | 2 hrs | ✅ |
| GET | `/vault/setup/verify` | Run system verification | 2 hrs | ✅ |
| POST | `/vault/setup/complete` | Finalize, lock setup endpoints | 1 hr | ✅ |

**Epic 8 Subtotal: ~115 hours**

## Epic 9: Quarantine Pipeline (Stages 1–3) ✅

File integrity, malware scanning, and content sanitization for everything entering the system.

| Task | Description | Effort | Status |
|------|-------------|--------|--------|
| 9.1 | Quarantine directory structure: isolated staging area, filesystem permissions | 2 hrs | ✅ |
| 9.2 | File type verification: magic byte checking, MIME validation (python-magic) | 4 hrs | ✅ |
| 9.3 | File structure validation: per-format deep validation (PDF, DOCX, JSON, JSONL, safetensors) | 6 hrs | ✅ |
| 9.4 | Size/count limits: configurable max file size, batch limits, storage alerts | 2 hrs | ✅ |
| 9.5 | Archive bomb detection: compression ratio checks, nested archive limits | 3 hrs | ✅ |
| 9.6 | ClamAV installation: offline config, pre-loaded signatures, systemd service | 3 hrs | (Ansible — separate infra task) |
| 9.7 | ClamAV scanning integration: Python service, result parsing, status mapping | 4 hrs | ✅ |
| 9.8 | YARA rule engine: custom rules for AI-specific threats | 6 hrs | ✅ |
| 9.9 | Hash blacklist: SHA-256 known-bad file database | 2 hrs | ✅ |
| 9.10 | Signature update mechanism: extract from USB update bundles, GPG verify | 4 hrs | ✅ |
| 9.11 | Signature staleness monitoring: age tracking, dashboard widget | 2 hrs | ✅ |
| 9.12 | PDF sanitization: strip JS/executables, rebuild clean (pikepdf) | 6 hrs | ✅ |
| 9.13 | Office document sanitization: strip macros/ActiveX/OLE (python-docx, openpyxl) | 6 hrs | ✅ |
| 9.14 | Image re-encoding: strip steganography via Pillow re-encode | 3 hrs | ✅ |
| 9.15 | Metadata scrubbing: EXIF, author info, XMP across all formats | 3 hrs | ✅ |
| 9.16 | Pipeline orchestrator: async job runner sequencing files through stages | 6 hrs | ✅ |
| 9.17 | Quarantine API endpoints (9 endpoints) | 6 hrs | ✅ |
| 9.18 | Quarantine hold workflow: admin review UI integration | 4 hrs | ✅ |
| 9.19 | Integration with upload flows: all file paths funnel through quarantine | 4 hrs | ✅ |
| 9.20 | Integration testing with known-bad files (EICAR, macro DOCX, etc.) | 6 hrs | ✅ (71 new tests) |

**Epic 9 Subtotal: ~75 hours**

## Epic 10: Update Mechanism

Air-gapped update lifecycle via USB bundles.

| Task | Description | Effort |
|------|-------------|--------|
| 10.1 | Update bundle format specification: directory structure, manifest, versioning scheme | 4 hrs |
| 10.2 | Build server tooling: script that packages containers, models, APT packages, ClamAV sigs, API code into signed bundle | 8 hrs |
| 10.3 | GPG signing pipeline: generate Vault AI signing key, sign bundles at build time | 3 hrs |
| 10.4 | USB detection: auto-detect mounted USB, scan for update bundles | 4 hrs |
| 10.5 | Signature verification: verify GPG signature before showing update to admin | 3 hrs |
| 10.6 | Update API endpoints (7 endpoints): scan, pending, apply, progress, rollback, history, status | 8 hrs |
| 10.7 | Update apply engine: load new containers into local registry, swap services, run migrations | 12 hrs |
| 10.8 | Database migration framework: versioned SQLite schema migrations, forward-only with rollback safety | 6 hrs |
| 10.9 | Rollback mechanism: retain previous container images + config, one-version rollback | 8 hrs |
| 10.10 | Health check gating: automatic rollback if health checks fail post-update | 4 hrs |
| 10.11 | Update progress UI: frontend component showing step-by-step progress | 4 hrs |
| 10.12 | End-to-end testing: full update cycle on test unit | 6 hrs |

**Epic 10 Subtotal: ~70 hours**

## Epic 11: Support & Diagnostics Tooling

| Task | Description | Effort |
|------|-------------|--------|
| 11.1 | Support bundle generator: `vault-support-bundle` packages logs, hardware info, system state, config (with secrets redacted) into encrypted archive | 6 hrs |
| 11.2 | Backup to USB: encrypted snapshot of all user data (conversations, API keys, audit logs, adapters, configs) | 8 hrs |
| 11.3 | Restore from backup: restore snapshot onto fresh or replacement unit | 6 hrs |
| 11.4 | Factory reset: admin-triggered full reset to golden image state (preserves hardware config) | 4 hrs |

**Epic 11 Subtotal: ~24 hours**

## Stage 3 Decisions Required

- [ ] **Database migration plan:** Stay with SQLite or move to PostgreSQL? (Recommendation: SQLite + SQLAlchemy ORM for now, migrate later if needed)
- [ ] **Update cadence committed:** Monthly? Quarterly? Drives staffing and process.
- [ ] **Backup encryption method:** Customer-provided passphrase or system-generated key?
- [ ] **Model hot-swap approach:** vLLM container restart (30-90s downtime) vs. investigating hot-reload? Need customer feedback from Rev 1 pilots.

## Stage 3 Exit Criteria

- [ ] Full API gateway operational (all 57 MVP endpoints)
- [ ] Quarantine pipeline scanning all file uploads (Stages 1–3)
- [ ] Update mechanism tested end-to-end: build bundle → USB transfer → apply → verify
- [ ] Backup/restore verified: can recover full user state onto replacement hardware
- [ ] Audit log captures every API request with user, action, and timestamp
- [ ] Admin can manage API keys, view system config, and restart services through API
- [ ] Product ready for sales to customers beyond pilot group

## Stage 3 Total Effort: 200–260 hours

---

# STAGE 4: Rev 3 — Data Platform

**Goal:** Transform from inference appliance into a data platform. Customers can upload documents, build RAG pipelines, and the quarantine gets AI-specific intelligence.
**Audience:** Existing customers expanding usage, new customers with document-heavy workflows (law firms, healthcare).
**Estimated effort:** 160–200 hours
**Target:** 8–12 weeks after Stage 3.

## Epic 12: Documents & RAG Pipeline

| Task | Description | Effort |
|------|-------------|--------|
| 12.1 | Document storage service: local encrypted storage for uploaded files | 4 hrs |
| 12.2 | Document chunking pipeline: split PDFs/DOCX/TXT into semantic chunks | 8 hrs |
| 12.3 | Embedding model integration: local embedding model (e.g., BGE, E5) running on dedicated GPU or CPU | 6 hrs |
| 12.4 | Vector database: ChromaDB or pgvector, local only, persistent storage | 6 hrs |
| 12.5 | RAG retrieval service: semantic search across indexed documents, ranked chunks | 8 hrs |
| 12.6 | RAG-augmented inference: inject retrieved context into chat completions automatically | 8 hrs |
| 12.7 | Collections API: create named document groups, manage membership | 4 hrs |
| 12.8 | Document API endpoints (8 endpoints): upload, list, detail, delete, search, collections CRUD | 8 hrs |
| 12.9 | Chat UI integration: document upload in conversations, show source citations | 10 hrs |
| 12.10 | End-to-end testing: upload → chunk → embed → retrieve → generate with citations | 6 hrs |

**Epic 12 Subtotal: ~68 hours**

## Epic 13: Quarantine Stage 4 — AI-Specific Safety

| Task | Description | Effort |
|------|-------------|--------|
| 13.1 | Training data format validation: JSONL structure, required fields, encoding | 4 hrs |
| 13.2 | Training data quality analysis: length distribution, class balance, duplicates, outliers | 6 hrs |
| 13.3 | Prompt injection detection: pattern matching + heuristic scoring for known injection patterns | 6 hrs |
| 13.4 | PII scanning engine: regex (SSN, credit card, phone, email, MRN) + spaCy NER (names, addresses, DOB) | 8 hrs |
| 13.5 | PII action configuration: admin choice of flag/redact/block, per-organization setting | 4 hrs |
| 13.6 | Model file validation: safetensors format enforcement, reject pickle, architecture verification, hash checking | 4 hrs |
| 13.7 | Data poisoning heuristics: statistical outlier detection, repetition analysis, perplexity scoring | 6 hrs |
| 13.8 | Integration testing with poisoned datasets and PII-laden files | 4 hrs |

**Epic 13 Subtotal: ~42 hours**

## Epic 14: LDAP/SSO Integration

| Task | Description | Effort |
|------|-------------|--------|
| 14.1 | LDAP/Active Directory connector: authenticate users against org directory | 8 hrs |
| 14.2 | User sync: pull user/group info from LDAP, map to API key scopes | 6 hrs |
| 14.3 | User management API endpoints (4 endpoints): list, create, update, deactivate | 6 hrs |
| 14.4 | Role-based access: map LDAP groups to Vault roles (user, power-user, admin) | 4 hrs |
| 14.5 | First-boot SSO setup: optional LDAP config step in setup wizard | 4 hrs |

**Epic 14 Subtotal: ~28 hours**

## Epic 15: WebSocket Endpoints

| Task | Description | Effort |
|------|-------------|--------|
| 15.1 | `ws://vault-cube.local/api/ws/inference` — real-time inference streaming (alternative to SSE) | 4 hrs |
| 15.2 | `ws://vault-cube.local/api/ws/system` — live system metrics push | 4 hrs |
| 15.3 | `ws://vault-cube.local/api/ws/logs` — live log streaming for admin | 4 hrs |
| 15.4 | `ws://vault-cube.local/api/ws/updates` — update progress streaming | 3 hrs |

**Epic 15 Subtotal: ~15 hours**

## Stage 4 Exit Criteria

- [ ] Users can upload documents and ask questions about them with cited sources
- [ ] PII scanning catches SSN, credit card, and MRN patterns in test data
- [ ] Quarantine Stage 4 flags prompt injections and data poisoning in training datasets
- [ ] LDAP integration tested against Active Directory and OpenLDAP
- [ ] WebSocket endpoints operational for real-time dashboard updates

## Stage 4 Total Effort: 160–200 hours

---

# STAGE 5: Rev 4 — Training Platform

**Goal:** Customers can fine-tune models on their own data and evaluate results — through the chat UI or programmatically.
**Audience:** Power users, research teams, organizations with domain-specific needs.
**Estimated effort:** 120–160 hours
**Target:** 8–12 weeks after Stage 4.

## Epic 16: Training & Fine-Tuning

| Task | Description | Effort |
|------|-------------|--------|
| 16.1 | Training job runner: background service wrapping Hugging Face `trl`/`peft` for LoRA/QLoRA | 12 hrs |
| 16.2 | GPU resource scheduler: queue training behind inference, configurable priority, optional dedicated GPU allocation | 8 hrs |
| 16.3 | Training API endpoints (9 endpoints): submit job, list, detail, cancel, list adapters, activate, deactivate, delete adapter, validate dataset | 12 hrs |
| 16.4 | Training progress tracking: loss curve, epoch progress, estimated time, real-time logs | 6 hrs |
| 16.5 | LoRA adapter management: versioning, metadata, storage, activation/deactivation on running model | 8 hrs |
| 16.6 | Chat UI guided training flow: conversational interface walks user through dataset upload, validation, config, and job submission | 12 hrs |
| 16.7 | Training data validation integration: require quarantine Stage 4 clearance before accepting datasets | 3 hrs |
| 16.8 | End-to-end testing: upload data → validate → train → adapter → inference with adapter | 6 hrs |

**Epic 16 Subtotal: ~67 hours**

## Epic 17: Evaluation & Benchmarking

| Task | Description | Effort |
|------|-------------|--------|
| 17.1 | Eval job runner: wraps `lm-evaluation-harness` + custom eval pipeline | 8 hrs |
| 17.2 | Eval API endpoints (5 endpoints): submit, list, detail, compare, quick-eval | 8 hrs |
| 17.3 | Eval results visualization: scores, per-example breakdown, model comparison charts | 8 hrs |
| 17.4 | Chat UI integration: "evaluate this model" flow, interactive quick-eval | 6 hrs |
| 17.5 | Pre-built eval datasets: ship standard benchmarks (MMLU, HumanEval, etc.) for out-of-box model comparison | 4 hrs |

**Epic 17 Subtotal: ~34 hours**

## Epic 18: Managed vs. Developer Mode Split

| Task | Description | Effort |
|------|-------------|--------|
| 18.1 | Mode concept in admin config: managed (default) vs. developer toggle | 3 hrs |
| 18.2 | Documentation: clear explanation of what developer mode enables and what support implications exist | 2 hrs |

**Epic 18 Subtotal: ~5 hours**

## Stage 5 Exit Criteria

- [ ] Customer can fine-tune a model on their data through chat UI without touching CLI
- [ ] LoRA adapters can be activated/deactivated for inference
- [ ] Eval jobs produce meaningful comparison between base model and fine-tuned adapter
- [ ] GPU scheduler prevents training from starving inference workloads
- [ ] Guided training flow tested with non-technical users (law firm persona)

## Stage 5 Total Effort: 120–160 hours

---

# STAGE 6: Rev 5 — Research Platform

**Goal:** Unlock direct hardware access for power users. The Vault Cube becomes a complete AI research workstation, not just an appliance.
**Audience:** University research labs, ML engineering teams.
**Estimated effort:** 60–80 hours
**Target:** As customer demand dictates.

## Epic 19: Developer Mode

| Task | Description | Effort |
|------|-------------|--------|
| 19.1 | Developer mode API endpoints (5 endpoints): enable, disable, status, launch Jupyter, stop Jupyter | 8 hrs |
| 19.2 | GPU allocation manager: admin selects which GPUs are reserved for dev vs. managed inference | 6 hrs |
| 19.3 | JupyterHub container: pre-built with PyTorch, common ML libraries, GPU access | 8 hrs |
| 19.4 | SSH access management: enable/disable, key-based auth, audit logging of sessions | 6 hrs |
| 19.5 | VS Code Server option: browser-based IDE connected to dev GPUs | 6 hrs |
| 19.6 | Resource monitoring: dev mode resource consumption visible in admin dashboard | 4 hrs |
| 19.7 | Custom container launching: admin can deploy arbitrary Docker containers on dev GPUs | 8 hrs |

**Epic 19 Subtotal: ~46 hours**

## Epic 20: Multi-Model Serving

| Task | Description | Effort |
|------|-------------|--------|
| 20.1 | Multi-model architecture: multiple vLLM instances, each on assigned GPUs, behind load-aware router | 12 hrs |
| 20.2 | Request routing: API gateway routes to correct model instance based on request's model parameter | 6 hrs |
| 20.3 | GPU allocation UI: visual GPU map showing what's running where, drag-and-drop reassignment | 8 hrs |

**Epic 20 Subtotal: ~26 hours**

## Stage 6 Exit Criteria

- [ ] Admin can enable developer mode, allocate GPUs, and launch JupyterHub
- [ ] Researcher can open Jupyter notebook and run custom PyTorch code on allocated GPU
- [ ] Multiple models can serve inference simultaneously on different GPU subsets
- [ ] All dev mode sessions logged to audit trail

## Stage 6 Total Effort: 60–80 hours

---

# FUTURE CONSIDERATIONS (Not Staged)

These are real customer needs we've identified but haven't committed to a stage. They will be prioritized based on customer feedback from earlier stages.

## Rackmount Form Factor
- Second SKU: 4U rackmount variant of the Vault Cube
- Different thermal engineering, rail kits, BMC/IPMI integration
- Likely driven by government/defense customer demand
- **Effort: TBD — significant hardware engineering, not just software**

## DoD / ITAR Compliance
- Trade Agreements Act (TAA) component sourcing
- DISA STIG compliance (beyond CIS Level 1)
- FedRAMP-adjacent documentation
- Country-of-origin auditing for all components
- **Effort: Legal + compliance + hardware procurement, 200+ hours**

## Multi-Unit Fleet Management
- Central management console for organizations with multiple Vault Cubes
- Fleet-wide model deployment, config push, update distribution
- Aggregate monitoring across units
- **Effort: Essentially a new product — 500+ hours**

## Prompt Injection Defense (Real-Time)
- Scan user prompts for injection attacks before sending to model
- Different problem from quarantine (real-time vs. batch, text vs. files)
- Potentially use a small classifier model as a pre-filter
- **Effort: 40–60 hours as a standalone epic**

## Custom Model Marketplace
- Curated library of models customers can download from Vault AI
- Subscription model for new model releases, delivered via update bundles
- **Effort: Product + business model design, 100+ hours**

---

# CUMULATIVE EFFORT SUMMARY

| Stage | Description | Endpoints | Effort | Cumulative | Status |
|-------|-------------|-----------|--------|------------|--------|
| Stage 1 | Foundation (Epics 1–2) | 0 | 60–75 hrs | 60–75 hrs | Epic 1 ✅, Epic 2.1–2.3 ✅ (GPU stack validated on GCP) |
| Stage 2 | Rev 1 — Pilot Product (Epics 3–7) | 3 + CLI + 29 frontend API + 7 setup | 120–160 hrs | 180–235 hrs | API ✅, UI ✅, Rev 2 API ✅, frontend wired ✅, first-boot wizard ✅, model type/status ✅, onboarding agent ✅, admin scope enforcement ✅, Epic 6 ✅ (monitoring) |
| Stage 3 | Rev 2 — Enterprise (Epics 8–11) | ~57 (partially done via Rev 2) | 200–260 hrs | 380–495 hrs | Epic 8 ✅ (64 endpoints, 239 tests), Epic 9 ✅ (quarantine pipeline: 9 endpoints, 71 tests, 310 total). Epics 10–11 remaining (updates, support). |
| Stage 4 | Rev 3 — Data Platform (Epics 12–15) | +27 | 160–200 hrs | 540–695 hrs | Planned |
| Stage 5 | Rev 4 — Training (Epics 16–18) | +14 | 120–160 hrs | 660–855 hrs | Planned |
| Stage 6 | Rev 5 — Research (Epics 19–20) | +8 | 60–80 hrs | 720–935 hrs | Planned |
| **Total** | **Full platform vision** | **~95** | **720–935 hrs** | | |

---

# KEY TECHNICAL DECISIONS LOG

Decisions made during planning, documented for reference.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Inference engine | vLLM 0.13.x (NGC container) | Industry standard, best multi-GPU support, OpenAI-compatible API, validated on RTX 5090/Blackwell via NGC |
| OS | Ubuntu 24.04 LTS | Long-term support, NVIDIA driver support, enterprise ecosystem |
| API framework | FastAPI | Async-native, fast, good OpenAPI docs, Python ecosystem |
| API format | Industry-standard (OpenAI-compatible) | Universal client compatibility — not vendor allegiance |
| Chat UI framework | Next.js 16 + React 19 + TypeScript | Professional appearance, SSR, app router, component reuse, not Gradio/Streamlit |
| Monitoring | Prometheus + Grafana (pre-configured, not custom-built) | Best-in-class, don't rebuild what exists |
| System admin | Cockpit (pre-configured, not custom-built) | Already handles logs, services, terminal, network |
| Database | SQLite + SQLAlchemy ORM (PostgreSQL migration path) | Simple for Rev 1, ORM enables future swap |
| Multi-GPU default | Replica parallelism with 32B-class models | Near-linear scaling, avoids PCIe bottleneck |
| File security | 4-stage quarantine pipeline | Stages 1–3 for MVP, Stage 4 for Phase 2 |
| Model format | safetensors only (reject pickle) | Security — pickle can execute arbitrary code |
| Abstraction layers | No LiteLLM for Rev 1; thin httpx client | Fewer dependencies, full control, add abstraction when multiple backends needed |
| API key management | Rev 1: CLI tool → Rev 2: API endpoints | Ship faster, formalize later |
| Training | Wrap HF trl/peft (not custom framework) | Proven libraries, don't build what exists |
| Fine-tuning via chat | System prompt + guided flow, not separate agent framework | Nearly free if chat UI exists, no LangChain complexity |

---

# RISK REGISTER

| Risk | Impact | Mitigation | Stage |
|------|--------|------------|-------|
| GPU hardware delays | Blocks Stages 1–2 entirely | Order immediately, identify backup suppliers | 1 |
| Model licensing issues | Could block commercial distribution | Legal review before committing to pre-loaded models | 1 |
| vLLM breaking changes | Pinned version may miss fixes | Pin and test thoroughly, monitor release notes for security patches | 1–2 |
| Thermal throttling (4× 5090) | Unpredictable performance drops | Benchmark under sustained load, per-GPU temp monitoring, thermal-aware routing | 1–2 |
| No pilot customer feedback | Building wrong features | Identify pilots during Stage 1, deploy Rev 1 ASAP | 2 |
| TLS/certificate UX | Poor first impression ("not secure" warnings) | First-boot wizard addresses TLS explicitly, provide CA distribution docs | 2 |
| SQLite write contention | Bottleneck under concurrent load | SQLAlchemy ORM enables PostgreSQL migration if needed | 3 |
| ClamAV signature staleness | Misses recent malware | Bundle fresh sigs with every update, dashboard warnings | 3 |
| Update mechanism bricking | Catastrophic for customer trust | Atomic rollback, health check gating, extensive testing | 3 |
| Scope creep across stages | Nothing ships | Treat stage boundaries as hard gates — don't pull forward | All |

---

# DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Oct 20, 2025 | CTO / AI Assistant | Initial blueprint: 5 epics, technical architecture |
| 2.0 | Oct 21, 2025 | CTO / AI Assistant | Research findings, removed MAAS/Harbor, revised epics |
| 3.0 | Oct 23, 2025 | CTO / AI Assistant | Detailed task breakdowns for Epics 1–2 |
| 4.0 | Feb 15, 2026 | CTO / AI Assistant | Complete restructure: 6 stages, 20 epics, 95 endpoints. Added API spec, quarantine pipeline, training platform, multi-GPU analysis, air-gapped architecture. Separated Rev 1 (3 endpoints) from full platform (95 endpoints). |
| 4.1 | Feb 16, 2026 | CTO / AI Assistant | Added completion status markers. Rev 2 frontend API support complete (28 endpoints, 97 tests). Marked Epic 3 ✅, Epic 4 ✅, partial Epic 8.3/8.4/8.5 ✅. Updated cumulative summary. |
| 4.2 | Feb 16, 2026 | CTO / AI Assistant | Status audit: marked frontend-backend integration complete in cumulative summary. Frontend now uses real API calls (no longer mock data) for all active features. |
| 4.3 | Feb 16, 2026 | CTO / AI Assistant | First-boot wizard backend complete: 7 endpoints (Epic 8.6 ✅), 19 new tests (117 total). Marked Epic 5.1, 5.9 done. Updated cumulative summary. |
| 4.4 | Feb 16, 2026 | CTO / AI Assistant | First-boot wizard frontend complete: 7-step form wizard wired to real backend API (Epic 5 ✅). Replaced mock onboarding (localStorage) with real setup flow — network, admin, TLS, model, verify, complete. App.tsx gate reordered: setup → auth → main app. |
| 4.5 | Feb 16, 2026 | CTO / AI Assistant | Model type/status fields: ModelInfo now includes type (chat/embedding) and status (running/available). Auto-classifies embedding models, fetches running state from Ollama /api/ps, sorts chat before embedding. Frontend filters embeddings from chat picker, shows running indicator, defaults to first running chat model. 134 tests. |
| 4.6 | Feb 16, 2026 | CTO / AI Assistant | Epic 7 complete (Onboarding Agent ✅): system prompt injection for first-time users — AI introduces Vault Cube, explains privacy, guides first task. Frontend-only change (useChat systemPrompt option, onboarding prompts, skip banner, localStorage flag). Also: backend .env auto-loading via Pydantic Settings, frontend .gitignore hardened for .env files. |
| 4.7 | Feb 21, 2026 | CTO / AI Assistant | Security: admin scope enforcement — all `/vault/admin/*` endpoints now require admin-scoped API key (was stored but never checked). New endpoint: `PUT /vault/admin/keys/{key_id}` for updating key metadata (label, active/disabled). 39 endpoints, 140 tests. Updated tech stack refs: frontend is Next.js 16 (migrated from Vite). |
| 4.8 | Feb 21, 2026 | CTO / AI Assistant | GPU track complete. Epic 1 tasks 1.8–1.10 ✅ (NVIDIA driver 570, CUDA 12.8, Container Toolkit, GCP integration test passed). Epic 2 tasks 2.1–2.3 ✅ (PyTorch 2.10+cu128, cuDNN 9.7, vLLM 0.13.0 via NGC container 26.01-py3, TensorFlow via NGC). Hardware spec resolved: 2× RTX 5090 FE (64GB VRAM), 256GB DDR5 ECC, 1 GPU currently installed. Updated hardware refs across all docs. |
| 4.9 | Feb 22, 2026 | CTO / AI Assistant | Epic 8 complete (Full API Gateway ✅). 24 new endpoints: audit query/export/stats (3), full config + TLS (4), text completions + embeddings + model detail (3), conversation export (1), expanded health + inference stats + services/restart/logs (5), model management — list/detail/load/unload/active/import/delete (7), WebSocket live metrics (1). 63 total endpoints, 234 tests. |
| 5.0 | Feb 22, 2026 | CTO / AI Assistant | Epic 6 complete (Monitoring Setup ✅): 4 Ansible roles (cockpit, prometheus, grafana, prometheus-alerts), Prometheus /metrics backend endpoint, 4 Grafana dashboards, 8 alert rules. 39 new files. 64 total endpoints, 239 tests. |
| 5.1 | Feb 21, 2026 | CTO / AI Assistant | Frontend wired to all Epic 8 endpoints: model management (load/unload/import/delete), audit log viewer with system logs tab, conversation export (JSON/Markdown), live inference stats, TLS certificate management, service management with restart, security settings tab. 9 new files, 9 modified files. New route: /audit. `npm run build` clean. |
| 5.2 | Feb 21, 2026 | CTO / AI Assistant | App deployment infrastructure complete: 5 new Ansible roles (nodejs, uv, vault-backend, vault-frontend, caddy), new app.yml playbook, systemd services for backend + frontend, Caddy reverse proxy with self-signed TLS. Three-playbook deployment: site.yml → gpu.yml → app.yml. Backend venv separated from PyTorch. Added python-multipart dependency. |
| 5.3 | Feb 21, 2026 | CTO / AI Assistant | Epic 9 complete (Quarantine Pipeline ✅). 3-stage security pipeline: file integrity (magic bytes, format validation, archive bombs), malware scanning (ClamAV client, YARA engine, hash blacklist), content sanitization (PDF JS stripping, Office macro removal, image re-encoding, metadata scrub). 9 new API endpoints, pipeline orchestrator with async background processing, signature management. 73 total endpoints, 310 tests. |
