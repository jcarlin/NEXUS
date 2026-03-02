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
                                │   ├── postgres (16-alpine)      │
                                │   ├── redis (7-alpine)          │
                                │   ├── qdrant (v1.13.2)          │
                                │   ├── neo4j (5-community)       │
                                │   ├── minio                     │
                                │   └── caddy (TLS termination)   │
                                └─────────────────────────────────┘

External APIs (unchanged):
  ├── Anthropic (Claude Sonnet 4.5) — reasoning
  └── OpenAI (text-embedding-3-large) — embeddings
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

# Redeploy after code changes
cd ~/nexus && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --build api worker
docker compose exec api alembic upgrade head

# Redeploy frontend
cd frontend/ && vercel --prod
```
