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
                                │   ├── qdrant (v1.13.2)          │
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
| e2-highmem-2 | 2 vCPU / 16GB | ~$68 | Full corpus, light usage |
| e2-standard-4 | 4 vCPU / 16GB | ~$98 | Full corpus, concurrent users |

Neo4j and Qdrant are the main memory consumers at scale. Resource limits in `docker-compose.cloud.yml` prevent any single service from OOM-killing the VM.

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
