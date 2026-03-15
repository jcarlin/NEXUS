# GCP Health Check & Error Report

Run a comprehensive health check on the production GCP instance. Checks VM status, all Docker services, resource usage, API health, error logs, and LangSmith traces. Compiles findings into a structured report.

## Constants

- **GCP Project:** `vault-ai-487703`
- **VM:** `nexus-demo`
- **Zone:** `us-central1-a`
- **Static IP:** `34.70.34.2`
- **Compose prefix:** `cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml`
- **SSH prefix:** `gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703 --quiet --command=`

## Steps

Run every `gcloud` command with `--project=vault-ai-487703` to avoid targeting the wrong GCP project.

All SSH commands use this pattern:
```bash
gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703 --quiet --command="<cmd>"
```

Compose commands must `cd ~/nexus` first:
```bash
gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703 --quiet --command="cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml <subcommand>"
```

### Step 1 — VM & Resource Status (run in parallel)

Run these 3 commands in parallel:

1. **VM status:**
```bash
gcloud compute instances describe nexus-demo --zone=us-central1-a --project=vault-ai-487703 --format="value(status)"
```

2. **Container status:**
```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml ps
```

3. **System resources:**
```bash
# via SSH
df -h / && echo '===MEMORY===' && free -h && echo '===UPTIME===' && uptime
```

### Step 2 — Health Endpoint

```bash
# via SSH
curl -sf http://localhost:8000/api/v1/health | python3 -m json.tool
```

If this fails, the API is down. Check API logs immediately and report RED status.

### Step 3 — Error Logs (run in parallel)

Run these 2 commands in parallel:

1. **API errors (last 200 lines):**
```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs api --tail=200 2>&1 | grep -iE 'error|exception|traceback|500|critical|failed' | tail -50
```

2. **Worker errors (last 200 lines):**
```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs worker --tail=200 2>&1 | grep -iE 'error|exception|traceback|failed' | tail -30
```

### Step 4 — Infrastructure Service Logs (run in parallel)

Run these 2 commands in parallel:

1. **Postgres (check for errors, connection issues):**
```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs postgres --tail=30 --since=24h
```

2. **All other infra services:**
```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs qdrant neo4j redis minio caddy --tail=15 --since=24h
```

### Step 5 — Recent API Activity

Check for 4xx/5xx responses and general traffic patterns:

```bash
# via SSH
cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs api --tail=100 --since=1h 2>&1 | tail -60
```

### Step 6 — LangSmith Traces

Use the LangSmith MCP tools to check for pipeline issues. Run these 2 calls in parallel:

1. **Errored runs:**
```
mcp__langsmith__fetch_runs(project_name="nexus", limit=20, error="true", is_root="true")
```

2. **High-latency runs (>10s):**
```
mcp__langsmith__fetch_runs(project_name="nexus", limit=10, filter='gt(latency, "10s")', is_root="true")
```

### Step 7 — Compile Report

Present findings in this format:

```
# GCP Instance Health Report — <timestamp>

## Status Summary: GREEN / YELLOW / RED

Criteria:
- GREEN: All core services healthy, no errors in last hour, disk < 70%, memory < 80%
- YELLOW: Non-critical service down (e.g., Flower), disk 70-85%, warnings present, or recoverable errors
- RED: Core service down (API, Postgres, Qdrant, Neo4j), disk > 85%, or persistent 5xx errors

## Services
| Service | Status | Notes |
|---------|--------|-------|
(per-service status from Steps 1-2)

## Resource Usage
| Resource | Used | Total | % | Assessment |
|----------|------|-------|---|------------|
(disk, memory, CPU from Step 1)

## Errors Found
(categorized by severity: HIGH / MEDIUM / LOW / INFO)
(include error message, location, impact, and fix recommendation)

## LangSmith Traces
(errored runs, high-latency runs, any anomalies)

## Recommendations
(numbered action items, ordered by priority)
```

## Known Issues (do not re-flag)

These are pre-existing and expected:
- `ollama.discover.failed` — No Ollama on GCP VM (uses Gemini APIs). Expected warning.
- `FLOWER_USER`/`FLOWER_PASSWORD` not set — Flower env vars not configured.
- Caddy Caddyfile formatting warning — cosmetic only.
- Caddy UDP buffer size warning for QUIC — non-blocking.

## Notes

- **Maximize parallelism.** Steps 1, 3, 4, and 6 each contain independent commands that should run in parallel.
- **API startup takes 60-90s.** If the VM was recently started, health check failure may be transient.
- **Worker logs use WARNING level** for structured log output. This is normal — check the log content, not just the level.
- **LangSmith traces from macOS** are from local dev, not the GCP instance. Filter by platform if needed.
