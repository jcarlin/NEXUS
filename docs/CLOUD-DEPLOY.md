# Cloud Demo Deployment (GCP + Vercel)

Single GCP VM running all backend services via Docker Compose + Caddy for TLS. Frontend SPA on Vercel.

## Architecture

```
Vercel (CDN)                    GCP Compute Engine VM
┌─────────────┐                 ┌─────────────────────────────────┐
│ React SPA   │──── HTTPS ────▶ │ Caddy (reverse proxy + TLS)    │
│ (static)    │                 │   ├── /api/* → FastAPI :8000    │
└─────────────┘                 │   └── /storage/* → MinIO :9000  │
                                │                                 │
                                │ Docker Compose                  │
                                │   ├── api (FastAPI)             │
                                │   ├── worker (Celery)           │
                                │   ├── ollama (embeddings, CPU)  │
                                │   ├── postgres (16-alpine)      │
                                │   ├── redis (7-alpine)          │
                                │   ├── qdrant (v1.17.1)          │
                                │   ├── neo4j (5-community)       │
                                │   ├── minio                     │
                                │   └── caddy (TLS termination)   │
                                └─────────────────────────────────┘

External APIs:
  └── Gemini (reasoning — query, analysis, ingestion tiers)
```

## Cost

| Resource | Monthly |
|----------|---------|
| GCE VM (e2-standard-2, 2 vCPU / 8GB) | ~$49 |
| 50GB SSD disk | ~$5 |
| Vercel (free tier) | $0 |
| Anthropic + OpenAI API (demo usage) | ~$5-25 |
| **Total** | **~$60-80/mo** |

Stop the VM when not demoing: `gcloud compute instances stop nexus-demo` (~$0.17/day for disk only).

---

## Step 1: GCP Infrastructure

```bash
# Create project + enable Compute Engine
gcloud projects create nexus-demo --name="NEXUS Demo"
gcloud config set project nexus-demo
gcloud services enable compute.googleapis.com

# Reserve static IP
gcloud compute addresses create nexus-ip --region=us-central1

# Create VM
gcloud compute instances create nexus-demo \
  --zone=us-central1-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-balanced \
  --tags=nexus-web \
  --address=$(gcloud compute addresses describe nexus-ip --region=us-central1 --format='value(address)')

# Firewall: only 80/443 + SSH
gcloud compute firewall-rules create nexus-allow-https \
  --action=ALLOW --rules=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 --target-tags=nexus-web

gcloud compute firewall-rules create nexus-allow-ssh \
  --action=ALLOW --rules=tcp:22 \
  --source-ranges=$(curl -s ifconfig.me)/32 --target-tags=nexus-web
```

### DNS

Point your domain's A record to the static IP. Caddy auto-provisions Let's Encrypt TLS.

---

## Step 2: Deploy Backend

```bash
# SSH into VM
gcloud compute ssh nexus-demo --zone=us-central1-a

# Install Docker
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable docker && sudo usermod -aG docker $USER
# Log out and back in for group change

# Clone repo
git clone <REPO_URL> ~/nexus && cd ~/nexus

# Configure environment
cp .env.cloud.example .env
nano .env  # Fill in: DOMAIN, API keys, passwords, JWT secret, CORS origins

# Build and start all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --build

# Run database migrations
docker compose exec api alembic upgrade head

# Create admin user
docker compose exec api python scripts/seed_admin.py
# Or with specific credentials:
# ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=yourpass docker compose exec api python scripts/seed_admin.py

# Verify
curl -s https://YOUR_DOMAIN/api/v1/health | python3 -m json.tool
```

---

## Step 3: Deploy Frontend (Vercel)

```bash
cd frontend/
npm install -g vercel
vercel login
vercel link  # Connect to Vercel project
```

**Vercel project settings** (dashboard or `vercel.json`):
- Framework: Vite
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`

**Environment variable** (Vercel dashboard → Settings → Environment Variables):
- `VITE_API_BASE_URL` = `https://YOUR_DOMAIN`

```bash
vercel --prod
```

---

## Step 4: Backend CORS

Update `.env` on the VM to allow Vercel origin:

```
CORS_ALLOWED_ORIGINS=https://your-app.vercel.app
```

Then restart the API:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml restart api
```

---

## Key Config Files

| File | Purpose |
|------|---------|
| `.env.cloud.example` | Cloud env var template (copy to `.env` on VM) |
| `Caddyfile` | Caddy reverse proxy config (API + MinIO + TLS) |
| `docker-compose.cloud.yml` | Overlay adding Caddy to the stack |
| `frontend/vercel.json` | Vercel build/routing config |
| `scripts/seed_admin.py` | Initial admin user creation |

## Key Environment Variables (Cloud-Specific)

| Variable | Purpose | Example |
|----------|---------|---------|
| `DOMAIN` | Caddy TLS domain | `api.nexus-demo.com` |
| `VITE_API_BASE_URL` | Frontend → backend URL (Vercel env) | `https://api.nexus-demo.com` |
| `MINIO_PUBLIC_ENDPOINT` | Public endpoint for presigned URLs | `api.nexus-demo.com/storage` |
| `CORS_ALLOWED_ORIGINS` | Allowed frontend origins | `https://nexus.vercel.app` |
| `FLOWER_USER` | Flower dashboard username | `admin` |
| `FLOWER_PASSWORD` | Flower dashboard password | (set a secure password) |

---

## Ollama (Local Embeddings)

The cloud overlay includes an Ollama service for on-VM embedding inference. This eliminates the OpenAI API dependency for embeddings and keeps document content on-machine.

### First-time setup

After the stack is running, pull the embedding model (one-time — persisted in `ollama_models` volume):

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

### Switching the embedding provider

Switch to Ollama embeddings via the **Admin UI** (Settings → LLM Configuration → Embedding Provider). No `.env` changes needed — the `OLLAMA_BASE_URL` is already configured in the cloud compose overlay.

**Important:** Switching embedding providers changes the vector space. Existing Qdrant vectors (e.g., OpenAI `text-embedding-3-large` at 3072d) are incompatible with `nomic-embed-text` (768d). A wipe + re-ingest is required after switching providers.

### Resource usage

- **Model:** `nomic-embed-text` (~274MB download, ~500MB loaded)
- **Memory limit:** 2GB (set in compose)
- **CPU inference:** ~25-30ms per chunk (no GPU required)

---

## Operations

```bash
# Stop VM (saves money)
gcloud compute instances stop nexus-demo --zone=us-central1-a

# Start VM
gcloud compute instances start nexus-demo --zone=us-central1-a

# View logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f caddy

# Redeploy backend (automated via CI/CD — see section below, or manually):
# cd ~/nexus && git pull
# docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --build api worker
# docker compose exec api alembic upgrade head

# Redeploy frontend
cd frontend/ && vercel --prod
```

---

## CI/CD (GitHub Actions)

Pushes to `main` auto-deploy to the GCP VM after backend tests pass (`.github/workflows/deploy.yml`).

### Required Setup

**Repository variables** (Settings → Variables → Actions):
- `GCE_INSTANCE` — VM name (e.g., `nexus-demo`)
- `GCE_ZONE` — VM zone (e.g., `us-central1-a`)

**Repository secrets** (Settings → Secrets → Actions):
- `GCP_SA_KEY` — Service account JSON key with `compute.instances.get` and OS Login or metadata SSH permissions
- `GCE_SSH_PRIVATE_KEY` — SSH private key whose public key is added to the VM (via `gcloud compute os-login ssh-keys add` or project metadata)

### How It Works

1. `Backend Tests` workflow runs on push to `main`
2. On success, `Deploy to GCP` triggers via `workflow_run`
3. Authenticates to GCP, SSHs into the VM
4. Runs `git fetch && git checkout origin/main`
5. Rebuilds `api` and `worker` containers
6. Runs `alembic upgrade head`
7. Waits for health check (60s timeout)

### Manual Deploy

If CI/CD is not configured, deploy manually:

```bash
gcloud compute ssh nexus-demo --zone=us-central1-a
cd ~/nexus && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --build api worker
docker compose exec api alembic upgrade head
```

---

## Operations & Maintenance

### Auto-Start (systemd)

Install the systemd unit so services start automatically after VM reboot:

```bash
# Copy the unit file (replace $USER with your VM username)
sudo cp deploy/nexus.service /etc/systemd/system/nexus@.service
sudo systemctl daemon-reload
sudo systemctl enable nexus@$USER

# Manual control
sudo systemctl start nexus@$USER
sudo systemctl stop nexus@$USER
sudo systemctl status nexus@$USER
```

### SSH Access

The SSH firewall rule uses your current public IP (`$(curl -s ifconfig.me)/32`). If your IP changes (residential ISP, VPN, mobile), you lose SSH access.

**Options:**
- **IAP tunnel (recommended):** `gcloud compute ssh nexus-demo --zone=us-central1-a --tunnel-through-iap` — no IP-based firewall rule needed
- **CIDR range:** Use a `/24` or `/16` range instead of `/32` if your IP is relatively stable
- **Update the rule:** `gcloud compute firewall-rules update nexus-allow-ssh --source-ranges=$(curl -s ifconfig.me)/32`

### Backups

No automated backups are configured by default. A `docker compose down -v` or disk failure destroys all data.

**PostgreSQL (scheduled dump):**
```bash
# Add to crontab: daily at 2 AM, keep 7 days
0 2 * * * docker compose -f ~/nexus/docker-compose.yml -f ~/nexus/docker-compose.prod.yml exec -T postgres pg_dump -U nexus nexus | gzip > ~/backups/nexus-pg-$(date +\%Y\%m\%d).sql.gz
0 3 * * * find ~/backups -name "nexus-pg-*.sql.gz" -mtime +7 -delete
```

**GCE disk snapshots (covers all Docker volumes):**
```bash
# Create a snapshot schedule (daily, keep 7)
gcloud compute resource-policies create snapshot-schedule nexus-daily \
  --region=us-central1 --max-retention-days=7 --daily-schedule
gcloud compute disks add-resource-policies nexus-demo \
  --resource-policies=nexus-daily --zone=us-central1-a
```

**Restore from snapshot:** Create a new disk from the snapshot, attach to a new VM, and `docker compose up`.

### Celery Monitoring (Flower)

Flower provides a web dashboard for monitoring Celery workers, active/pending tasks, and task history.

**Setup** (one-time):

Add credentials to `~/nexus/.env` on the VM:

```bash
FLOWER_USER=admin
FLOWER_PASSWORD=<secure-password>
```

Then recreate the Flower container:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --force-recreate flower
```

**Access via SSH tunnel** (Flower is bound to `127.0.0.1` only — not publicly exposed):

```bash
# Open tunnel (keep this terminal open)
gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703 -- -L 5555:localhost:5555

# Then open in browser:
# http://<user>:<password>@localhost:5555/flower/
```

The basic auth prompt may not appear in all browsers — embedding credentials in the URL is the reliable method.

**In-app alternative:** The frontend also has a Celery panel at **Admin → Operations → Celery Workers** that shows worker status, active tasks, and queue controls via the API (no SSH tunnel needed).

### Monitoring & Alerting

**GCP uptime check:**
```bash
# Create an HTTPS uptime check on the health endpoint
gcloud monitoring uptime create nexus-health \
  --display-name="NEXUS API Health" \
  --resource-type=uptime-url \
  --hostname=YOUR_DOMAIN \
  --path=/api/v1/health \
  --protocol=https \
  --period=300
```

**Recommended alert thresholds:**
- CPU sustained > 80% for 5 min
- Memory usage > 90%
- Disk usage > 85%
- Uptime check failure (2 consecutive)

Configure alerts in GCP Console → Monitoring → Alerting, or via `gcloud alpha monitoring policies create`.

### VM Sizing

The default **e2-standard-2** (2 vCPU / 8GB) is adequate for demos with a small corpus (< 5k pages). For the full 50k+ page corpus:

| Machine Type | Specs | Monthly Cost | Use Case |
|---|---|---|---|
| e2-standard-2 | 2 vCPU / 8GB | ~$49 | Demo, small corpus |
| e2-custom-8-24576 | 8 vCPU / 24GB | ~$175 | Full corpus, CPU-only |
| n1-standard-8 + T4 | 8 vCPU / 30GB + 16GB VRAM | ~$186 (spot) | Full corpus, GPU-accelerated |
| g2-standard-8 (L4) | 8 vCPU / 32GB + 24GB VRAM | ~$249 (spot) | Full corpus, best GPU option |

**Per-worker memory: ~5.7GB** (Docling ~1GB, GLiNER ~600MB, sparse embedder ~300MB, torch ~800MB, working memory ~3GB). Max 3 workers on 24GB, 4 on 30GB.

### GPU VM Setup

For GPU-accelerated inference (20x faster embeddings, 20x faster reranking):

```bash
# Create VM with T4 GPU (spot pricing)
gcloud compute instances create nexus-gpu \
  --zone=us-west1-a \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --image-family=common-cu128-ubuntu-2404-nvidia-570 \
  --image-project=deeplearning-platform-release \
  --boot-disk-size=100GB --boot-disk-type=pd-ssd \
  --tags=nexus-web \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --maintenance-policy=TERMINATE

# Install Docker + NVIDIA Container Toolkit
curl -fsSL https://get.docker.com | sh
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Start the stack with the GPU overlay:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml -f docker-compose.gpu.yml up -d
```

The GPU overlay adds NVIDIA passthrough to Ollama and optionally a TEI embedder. See `docker-compose.gpu.yml` for details.

### Ingestion VM Setup

For bulk ingestion of large corpora (10k+ documents), use a high-CPU VM with the ingestion overlay:

```bash
gcloud compute instances create nexus-ingest \
  --zone=us-west1-a \
  --machine-type=e2-standard-16 \
  --boot-disk-size=250GB --boot-disk-type=pd-ssd \
  --tags=nexus-web
```

Start the stack with the ingestion overlay:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml -f docker-compose.ingest.yml up -d
```

The ingestion overlay (`docker-compose.ingest.yml`) splits workers into two dedicated pools to prevent queue starvation:

| Service | Default Replicas | Queues | Purpose |
|---------|-----------------|--------|---------|
| `worker` | 2 | default, bulk, background | I/O-bound import tasks (embedding API, Qdrant writes) |
| `ner-worker` | 2 | ner | CPU-bound GLiNER entity extraction (8GB memory limit) |

Both worker types set `OMP_NUM_THREADS=2` and `MKL_NUM_THREADS=2` to prevent PyTorch/numpy from consuming all cores via thread parallelism.

**Tuning (set in `.env` on the VM):**
```bash
INGEST_WORKER_REPLICAS=2      # General worker replicas
NER_WORKER_REPLICAS=2         # NER worker replicas
CELERY_CONCURRENCY=1          # Tasks per general worker process
NER_WORKER_CONCURRENCY=1      # Tasks per NER worker process
DEFER_NER_TO_QUEUE=true       # Required: dispatch NER to separate queue
```

**Scaling dynamically** (no rebuild needed):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml -f docker-compose.ingest.yml \
  up -d --scale worker=3 --scale ner-worker=3 --no-recreate
```

**Per-worker memory guideline:** ~5.7GB (Docling ~1GB, GLiNER ~600MB, sparse embedder ~300MB, torch ~800MB, working memory ~3GB). On a 64GB VM, 4-6 total workers is safe with infrastructure services overhead.

**Data safety:** All workers use `acks_late=True` + `reject_on_worker_lost=True`. Restarting or scaling workers is always safe — in-flight tasks are redelivered by RabbitMQ.

**Disk snapshots (weekly backup):**
```bash
gcloud compute resource-policies create snapshot-schedule nexus-gpu-weekly \
  --region=us-west1 --max-retention-days=30 --weekly-schedule=sunday --start-time=04:00
gcloud compute disks add-resource-policies nexus-gpu \
  --zone=us-west1-a --resource-policies=nexus-gpu-weekly
```

### Rollback

If a deploy breaks the API:

```bash
# Revert to a known-good commit
cd ~/nexus
git log --oneline -10  # Find the last working commit
git checkout <sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --build api worker

# If migrations need reverting
docker compose exec api alembic downgrade -1
```

For safer rollbacks, consider tagging releases: `git tag v1.0.0` before each deploy.
