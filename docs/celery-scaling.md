# Celery Worker Scaling Guide

Operational runbook for scaling Celery workers on the GCP VM without restarting services or affecting in-flight jobs.

## Current Setup

- **VM**: `nexus-demo` (e2-custom-8-24576, 8 vCPU / 24GB RAM)
- **Workers**: 2 containers (`deploy.replicas: 2` in `docker-compose.prod.yml`)
- **Concurrency**: 1 prefork child per container (`-c 1`)
- **Effective parallelism**: 2 tasks at a time
- **Queues**: `default` (ingestion), `bulk` (batch ops), `background` (entity resolution, analysis, exports)

### Why Hot-Scaling Is Safe

| Setting | Value | Effect |
|---|---|---|
| `task_acks_late` | `True` | Tasks acknowledged only after completion; crash = auto-requeue |
| `reject_on_worker_lost` | `True` (on ingestion tasks) | Immediate requeue if worker dies mid-task |
| `worker_prefetch_multiplier` | `1` | Each worker prefetches only 1 task; no "stolen" work |
| `--pool=prefork` | (command line) | Supports `pool_grow`/`pool_shrink` remote control |

---

## Option A: Add Worker Replicas (Recommended)

Adds new containers without touching existing ones. Best for production ingestion.

### Scale Up

```bash
# SSH into the VM
gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703
cd ~/nexus

# Add a 3rd worker (existing 2 are NOT restarted)
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  up -d --scale worker=3 --no-recreate
```

### Verify

```bash
# Check container count and uptime (new container should show seconds, existing show hours/days)
sudo docker ps --filter "name=nexus-worker" --format "table {{.Names}}\t{{.Status}}"

# Confirm all workers are connected
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app inspect ping
```

### Scale Down

```bash
# Remove the 3rd worker
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  up -d --scale worker=2 --no-recreate
```

If the 3rd worker is mid-task when scaled down, the task requeues automatically (`acks_late` + `reject_on_worker_lost`).

### Properties

| Property | Value |
|---|---|
| Concurrency gain | 2 -> 3 (+50%) per additional replica |
| Memory cost | ~5.7GB per additional worker (after model loading) |
| Survives container restart | Yes |
| Survives `docker compose up -d` | No (reverts to `replicas: 2` from compose file) |
| Isolation | Full container isolation; OOM in one doesn't affect others |

---

## Option B: Grow Prefork Pool (Ephemeral)

Adds child processes inside existing containers via Celery remote control. More throughput, less isolation.

### Grow Pool

```bash
# Add 1 child process to ALL workers (broadcasts via Redis)
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app control pool_grow 1
```

### Verify

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app inspect stats | grep -A 5 "pool"
```

### Shrink Pool

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app control pool_shrink 1
```

### Properties

| Property | Value |
|---|---|
| Concurrency gain | 2 -> 4 (+100%) with `pool_grow 1` on 2 workers |
| Memory cost | ~5.7GB per additional child (after model loading) |
| Survives container restart | **No** (resets to `-c 1`) |
| Isolation | Children share container; OOM kills both |

---

## Comparison

| Factor | Option A (replicas) | Option B (pool_grow) |
|---|---|---|
| Concurrency gain | +1 per replica | +2 total (1 per worker) |
| Memory cost | +5.7GB per replica | +11.4GB total |
| Persistence | Survives restarts | Ephemeral |
| Isolation | Full container | Shared container |
| Best for | Production, long-running ingestion | Quick temporary boost |

---

## Memory Budget

| Component | Estimated RAM |
|---|---|
| PostgreSQL | ~1.5GB |
| Qdrant | ~1-2GB |
| Neo4j (heap capped at 2G) | ~2GB |
| Redis + MinIO + Flower | ~500MB |
| Ollama (nomic-embed-text) | ~1.5GB |
| API (uvicorn) | ~500MB |
| 2 workers (baseline) | ~11.4GB |
| **Total (baseline)** | **~18-19GB** |

**Safe scaling limits on 24GB VM (per-worker RSS observed: ~5.7GB):**
- 3 workers x 1 child = ~23GB (max safe — nearly full)
- 4 workers x 1 child = ~29GB (OOM — confirmed by incident 2026-03-22)
- 5 workers x 1 child = ~34GB (OOM — killed SSH daemon)

**Do not exceed 3 workers on a 24GB VM.**

---

## Monitoring

```bash
# VM memory
free -h

# Per-container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"

# Queue depth (tasks waiting)
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app inspect reserved

# Active tasks
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml \
  exec worker celery -A workers.celery_app inspect active

# Flower dashboard
# http://34.70.34.2:5555/flower/
```

---

## Making Changes Permanent

To persist a replica count change, edit `docker-compose.prod.yml`:

```yaml
# Line 50
deploy:
  replicas: 3  # was 2
```

To persist a concurrency change, edit the command on line 48:

```
command: celery -A workers.celery_app worker -Q default,bulk,background -l info -c 2 --pool=prefork --max-tasks-per-child=100
```

Either change requires `docker compose up -d` to apply. This recreates worker containers, but in-flight tasks requeue safely due to `acks_late`.
