# CLAUDE.md — Vault AI Systems

> **Note:** This is a **parent folder**, not a git repo for the sub-projects. Each sub-directory (`vault-ai-frontend/`, `vault-ai-backend/`, `vault-ai-os/`) is its own independent git repository. Run git commands from within the appropriate sub-directory.

## Current Sprint (February 2026)

**Two parallel tracks running:**

| Track | Owner | Status | Tasks |
|-------|-------|--------|-------|
| **GPU & Inference** | Colleague | ✅ Complete | NVIDIA 570 → CUDA 12.8 → Container Toolkit → PyTorch → TensorFlow (NGC) → vLLM (NGC) — validated on GCP Feb 2026 |
| **API Gateway** | Julian | ✅ Complete | FastAPI gateway, 64 endpoints (3 Rev 1 + 28 Rev 2 + 7 first-boot + 1 key update + 24 Epic 8 + 1 metrics), auth, CLI, Docker, 239 tests |
| **Monitoring** | Julian | ✅ Complete | Epic 6: Cockpit, Prometheus, Grafana (4 dashboards), alert rules (8), /metrics endpoint |
| **Frontend → Epic 8** | Julian | ✅ Complete | Model mgmt, audit log, conversation export, inference stats, TLS, services, security settings — all wired to backend |
| **App Deployment** | Julian | ✅ Complete | 5 Ansible roles (nodejs, uv, vault-backend, vault-frontend, caddy), app.yml playbook, systemd services, Caddy reverse proxy |

**Merge point:** GPU track done — deploy API gateway on the Cube, swap mock for real vLLM, test end-to-end.

**What's done:** Epic 1 complete (golden image base + GPU stack validated), Epic 2 tasks 2.1–2.3 (PyTorch, CUDA/cuDNN, vLLM via NGC containers), chat UI (complete, wired to real backend API), API gateway Rev 1 (3 endpoints, 50 tests), Rev 2 frontend API support (28 endpoints, 97 total tests), frontend-backend integration (chat streaming, conversations, admin, settings, insights — all using real API calls), first-boot wizard complete (backend: 7 endpoints, 117 tests; frontend: 7-step form wizard wired to real API), Epic 8 complete (Full API Gateway: 24 new endpoints — audit, config, TLS, completions, embeddings, model management, system monitoring, WebSocket; 234 tests), Epic 6 complete (Monitoring Setup: Cockpit, Prometheus, Grafana with 4 dashboards, 8 alert rules, /metrics endpoint; 239 tests), landing page (Epic 6.4), Cube assembled and running Ubuntu Desktop, frontend wired to all Epic 8 endpoints (model management, audit log, conversation export, inference stats, TLS, services), app deployment roles complete (5 new Ansible roles: nodejs, uv, vault-backend, vault-frontend, caddy; new app.yml playbook; systemd services for backend + frontend; Caddy reverse proxy with TLS).

**What's next:** Deploy on the Cube (run site.yml → gpu.yml → app.yml), swap mock for real vLLM, end-to-end test → pilot customer deployment.

---

## Project Overview

Vault AI Systems is a self-hosted, air-gapped AI inference and fine-tuning platform for enterprise deployments. Ships air-gapped by default (LAN available, internet optional) — no cloud dependencies, no data leaves the building.

**Product:** The Vault Cube — a turnkey hardware appliance with 2× RTX 5090 FE (1 currently installed), pre-configured OS, AI inference engine, and management UI. Price point: $40–60K.

**Target users:** Enterprise teams (5–100 concurrent users) needing private LLM inference. Universities, law firms, healthcare, government, financial services.

**Team:** Solo dev + AI assistance + colleague on GPU/infra, 3–6 month timeline.

**Current stage:** Stage 2 (Rev 1 — Shippable Pilot Product). See `ROADMAP.md` for full 6-stage plan.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VAULT AI SYSTEMS                         │
│                                                                 │
│  vault-ai-frontend/       vault-ai-backend/     vault-ai-os/
│  (Frontend)                (Backend API)         (Infrastructure)
│  Next.js + React + TS      FastAPI + vLLM        Packer + Ansible
│  ───────────────           ──────────────        ────────────────
│  Chat UI ✅ complete       /v1/chat/completions  Golden VM images
│  Model management          /v1/models            GPU driver setup ✅
│  Training dashboard        /vault/health         Security hardening
│  Cluster monitoring        API key auth          Air-gap packaging
│  Insights/analytics        Request logging       Multi-target builds
│                            vLLM proxy
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              HARDWARE: Vault Cube Workstation               ││
│  │  2× RTX 5090 FE (64GB VRAM, 1 installed) · Threadripper PRO 7975WX ││
│  │  256GB DDR5 ECC · 8TB NVMe · Ubuntu 24.04 LTS             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Repo Structure

```
vault-ai-systems/
├── CLAUDE.md                    # This file — root project guide
├── ROADMAP.md                   # Master product roadmap (6 stages, 20 epics)
│
├── vault-ai-frontend/          # Frontend — chat UI and management dashboards
│   ├── src/components/          # Chat, cluster, insights, models, training, settings
│   ├── src/hooks/               # useChat, useTrainingJobs, etc.
│   ├── src/lib/api/             # API client layer (fetch wrappers, SSE streaming)
│   ├── src/mocks/               # Legacy mock data (mostly types/utilities now, data comes from backend)
│   └── CLAUDE.md                # Frontend-specific guidance
│
├── vault-ai-backend/            # Backend API — FastAPI gateway to vLLM
│   ├── app/                     # Application code
│   ├── tests/                   # Unit + integration tests
│   ├── docker/                  # Dockerfiles + compose
│   ├── CLAUDE.md                # Backend-specific guidance + conventions
│   ├── vault-api-spec.md        # API endpoint specification (all revisions)
│   └── PRD.md                   # Full backend design reference (future scope)
│
└── vault-ai-os/                 # Infrastructure — golden image builder
    ├── packer/                  # Packer templates (VBox, QEMU, GCP)
    ├── ansible/                 # Provisioning roles (site.yml + gpu.yml + app.yml)
    ├── scripts/                 # Build/validation scripts
    ├── docs/                    # GPU runbook, architecture docs
    └── CLAUDE.md                # Infra-specific guidance
```

---

## Tech Stack

| Layer | Rev 1 (Now) | Later Stages | Status |
|-------|-------------|--------------|--------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui | — | ✅ Complete |
| **API Gateway** | FastAPI, httpx, SQLite, uvicorn | PostgreSQL, Celery+Redis | ✅ Complete (64 endpoints, 239 tests) |
| **Inference** | vLLM 0.13.x (NGC container), validated on Blackwell | Tensor parallel, multi-model | ✅ Validated on GCP |
| **Auth** | API keys (hashed in SQLite) | JWT + LDAP/SSO | Rev 1 scope |
| **Training** | — | Axolotl, LoRA/QLoRA, job queue | Stage 5 |
| **Monitoring** | Prometheus + Grafana + Cockpit (pre-configured) | Custom dashboards | ✅ Complete (Epic 6) |
| **Reverse Proxy** | Caddy (self-signed TLS) | ACME auto-TLS when internet enabled | ✅ Complete (Ansible caddy role) |
| **Infrastructure** | Packer, Ansible, Ubuntu 24.04 LTS | — | ✅ Base + GPU + app deployment |

---

## Development Commands

### Frontend (vault-ai-frontend/)
```bash
cd vault-ai-frontend
npm install
npm run dev          # Dev server (Next.js)
npm run build        # Production build
npm run start        # Production server
```

### Backend (vault-ai-backend/)
```bash
cd vault-ai-backend
uv sync                                          # Install deps
VLLM_BASE_URL=http://localhost:8001 uvicorn app.main:app --reload   # Dev (mock vLLM)
uvicorn app.main:app --reload                    # Dev (real vLLM)
pytest                                           # Run tests
vault-admin create-key --label "Test" --scope user   # Create API key
```

### Infrastructure (vault-ai-os/)
```bash
cd vault-ai-os/packer
packer validate ubuntu-22.04-demo-box.pkr.hcl
packer build ubuntu-22.04-demo-box.pkr.hcl

cd ../ansible
ansible-playbook -i localhost, -c local playbooks/site.yml          # Base system
ansible-playbook -i localhost, -c local playbooks/gpu.yml -vv       # GPU stack
ansible-playbook -i localhost, -c local playbooks/site.yml --tags docker,python
ansible-playbook -i localhost, -c local playbooks/app.yml -vv       # App stack (backend + frontend + Caddy)
ansible-playbook -i localhost, -c local playbooks/app.yml --tags backend
```

---

## Key Documents

| File | Purpose | Read When |
|------|---------|-----------|
| `ROADMAP.md` | Master product roadmap: 6 stages, 20 epics, all endpoints, effort estimates | Understanding what ships when |
| `vault-ai-backend/vault-api-spec.md` | API endpoint specification: all endpoints (Rev 1–5), request/response formats, auth | Understanding the API contract, building integrations |
| `vault-ai-backend/PRD.md` | Full backend design: DB schema, training architecture, system design | Planning backend features beyond Rev 2 |
| `vault-ai-backend/CLAUDE.md` | Backend coding conventions, current scope, how to run/test | Writing backend code |
| `vault-ai-frontend/CLAUDE.md` | Frontend components, API integration, pages, design tokens | Working on frontend |
| `vault-ai-os/CLAUDE.md` | Packer/Ansible commands, build pipeline, role layers, GPU deployment | Working on infrastructure |

---

## Stage Summary (from ROADMAP.md)

| Stage | What Ships | Effort | Status |
|-------|-----------|--------|--------|
| **Stage 1: Foundation** | Bootable hardened system with inference on GPUs | 60–75 hrs | ✅ Complete (Epic 1 + Epic 2.1–2.3) |
| **Stage 2: Rev 1+2** | Pilot product: 38 API endpoints, chat UI, first-boot wizard, monitoring | 120–160 hrs | API ✅, UI ✅, Setup ✅, GPU ✅, Monitoring ✅, Frontend→Epic 8 ✅ (64 endpoints, 239 tests) |
| **Stage 3: Rev 2** | Enterprise features: full API (57 endpoints), quarantine, updates, backup | 200–260 hrs | Epic 8 ✅ (backend + frontend). Epics 9–11 remaining. |
| **Stage 4: Rev 3** | Data platform: RAG, document upload, PII scanning, LDAP | 160–200 hrs | Planned |
| **Stage 5: Rev 4** | Training: fine-tuning via chat UI, eval, adapters | 120–160 hrs | Planned |
| **Stage 6: Rev 5** | Research: developer mode, JupyterHub, multi-model serving | 60–80 hrs | Planned |

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Inference engine | vLLM (not llama.cpp for prod) | Continuous batching, multi-GPU, 793 vs 41 TPS |
| API format | Industry-standard (OpenAI-compatible) | Universal client compatibility |
| Multi-GPU default | Replica parallelism (1 copy per GPU, scales to 2–4 GPUs) | Near-linear scaling, avoids PCIe bottleneck |
| Rev 1 database | SQLite + SQLAlchemy ORM | Simple now, PostgreSQL swap later via ORM |
| Rev 1 auth | API keys (not JWT) | Simpler for air-gapped, no token refresh needed |
| Rev 1 model config | Config files + CLI tools | Don't build API endpoints for things done once |
| Chat UI framework | Next.js + React (not Gradio/Streamlit) | Professional appearance for $50K product, SSR, app router |
| Monitoring | Grafana + Cockpit (pre-configured, not custom) | Don't rebuild what exists |
| Everything through API | All inference goes through FastAPI gateway | Audit trail, auth, rate limiting, backend swappable |
| Cube deployment | 3-playbook Ansible pipeline (site.yml → gpu.yml → app.yml) | Separation of concerns: base system, GPU stack, application stack |
| Backend venv | Separate `/opt/vault/backend-venv` (not shared with PyTorch) | Avoid dependency conflicts, faster startup, independent updates |

---

## GPU Configuration (Rev 1)

**Current hardware:** 1× RTX 5090 FE installed (32GB VRAM). Second GPU on hand, not yet installed. Target config is 2× GPUs in **replica mode** — each running an independent copy of a 32B-class model for near-linear throughput scaling.

**Deployment approach:** vLLM runs via NGC container (`nvcr.io/nvidia/vllm-inference:26.01-py3`) on Blackwell GPUs. TensorFlow also via NGC container. Convenience scripts (`vllm-serve`, `vllm-shell`, `tensorflow-shell`) installed by the Ansible gpu.yml playbook.

```yaml
# /opt/vault/config/gpu-config.yaml (Rev 1)
strategy: replica
models:
  - id: qwen2.5-32b-awq
    gpus: [0]           # Currently 1 GPU; add GPU 1 when second installed
    mode: replica
```

Training and split GPU modes come in Stage 5 when fine-tuning ships.

---

## Conventions

- **Frontend**: Path alias `@/` → `./src/`, `cn()` for classnames, dark theme (zinc-950), status colors (emerald/amber/red)
- **Backend**: See `vault-ai-backend/CLAUDE.md` for full conventions. Key rules: async everywhere, SQLAlchemy ORM, Pydantic v2, httpx for vLLM proxy, structured JSON logging.
- **Infra**: Default creds `vaultadmin/vaultadmin`, idempotent Ansible (run 3x, 0 changes on 2-3)
- **General**: Never save working files to repo root. Use appropriate subdirectories.
