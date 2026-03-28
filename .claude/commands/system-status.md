# Local System Status & Ingestion Health Check

Run a comprehensive health check on the LOCAL development environment. Checks all Docker services, API health, resource usage, data inventory, cross-store integrity, ingestion pipeline, Celery worker efficiency, error state analysis, and LLM/embedding health. Compiles findings into a structured report.

This is for LOCAL dev (`make dev` or Docker Compose). For GCP production, use `/health-check` instead.

## Constants

- **API base URL:** `http://localhost:8000`
- **Auth:** `admin@nexus-demo.com` / `nexus-demo-2026`
- **Default matter ID:** `00000000-0000-0000-0000-000000000001`
- **RabbitMQ management:** `http://localhost:15672` (credentials from `RABBITMQ_USER`/`RABBITMQ_PASSWORD` in `.env`)
- **Qdrant HTTP:** `http://localhost:6333`
- **Neo4j:** credentials from `NEO4J_USER`/`NEO4J_PASSWORD` in `.env`
- **PostgreSQL:** `docker compose exec -T postgres psql -U nexus -d nexus -c`
- **Redis:** `docker compose exec -T redis redis-cli`

## Steps

### Step 0 — Environment & Authentication

Source `.env` to load credentials, then obtain a JWT token for admin API calls.

```bash
set -a && source .env && set +a
```

```bash
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@nexus-demo.com","password":"nexus-demo-2026"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token obtained: ${TOKEN:+yes}"
```

If this fails, the API server is down. Set `API_DOWN=true` mentally and proceed with Docker/CLI fallbacks for all subsequent steps. The skill should still produce a useful report without the API — only Steps that explicitly say "(auth)" will be skipped.

### Step 1 — Service Health (run in parallel)

Run these 4 commands in parallel:

1. **Docker container status + resource usage:**
```bash
docker compose ps && echo '===DOCKER STATS===' && docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

2. **API health endpoint:**
```bash
curl -sf http://localhost:8000/api/v1/health | python3 -m json.tool
```

3. **Admin container details** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  http://localhost:8000/api/v1/admin/operations/containers | python3 -m json.tool
```

4. **Direct service pings** (fallback — always run these to verify independently):
```bash
echo "=== Redis ===" && docker compose exec -T redis redis-cli ping && \
echo "=== Qdrant ===" && curl -sf http://localhost:6333/healthz && \
echo "=== Neo4j ===" && curl -sf -o /dev/null -w "%{http_code}" http://localhost:7474/ && echo && \
echo "=== RabbitMQ ===" && curl -sf -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" http://localhost:15672/api/healthchecks/node 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "not running (Redis broker mode)" && \
echo "=== PostgreSQL ===" && docker compose exec -T postgres pg_isready -U nexus -d nexus && \
echo "=== MinIO ===" && curl -sf -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live && echo
```

### Step 2 — Resource Usage (run in parallel)

Run these 4 commands in parallel:

1. **System metrics via API** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  http://localhost:8000/api/v1/admin/operations/system-metrics | python3 -m json.tool
```

2. **Host disk + Docker volumes:**
```bash
df -h / && echo '===DOCKER DISK===' && docker system df 2>/dev/null
```

3. **PostgreSQL database size:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT pg_size_pretty(pg_database_size('nexus')) AS db_size,
       (SELECT count(*) FROM pg_stat_activity WHERE datname = 'nexus') AS active_connections;
"
```

4. **Qdrant collection sizes:**
```bash
curl -sf http://localhost:6333/collections/nexus_text | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print(f\"nexus_text: {d['points_count']} points, indexed={d['indexed_vectors_count']}, segments={d.get('segments_count','?')}, status={d['status']}\")
" 2>/dev/null || echo "nexus_text: unavailable"

curl -sf http://localhost:6333/collections/nexus_visual | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print(f\"nexus_visual: {d['points_count']} points, status={d['status']}\")
" 2>/dev/null || echo "nexus_visual: not created"
```

### Step 3 — Data Inventory (run in parallel)

Run these 4 commands in parallel:

1. **PostgreSQL document stats:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT count(*) AS total_docs,
       coalesce(sum(page_count),0) AS total_pages,
       coalesce(sum(chunk_count),0) AS total_chunks,
       coalesce(sum(entity_count),0) AS total_entities,
       pg_size_pretty(coalesce(sum(file_size_bytes),0)::bigint) AS total_file_size
FROM documents;
"
```

2. **Qdrant points per collection:**
```bash
curl -sf http://localhost:6333/collections | python3 -c "
import sys,json,urllib.request
for c in json.load(sys.stdin)['result']['collections']:
    name = c['name']
    try:
        info = json.loads(urllib.request.urlopen(f'http://localhost:6333/collections/{name}').read())
        r = info['result']
        print(f\"{name}: {r['points_count']} points, {r['indexed_vectors_count']} indexed, status={r['status']}\")
    except: print(f\"{name}: error reading\")
"
```

3. **Neo4j node and relationship counts:**
```bash
docker compose exec -T neo4j cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-changeme}" \
  "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;" 2>/dev/null && \
echo '===RELATIONSHIPS===' && \
docker compose exec -T neo4j cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-changeme}" \
  "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC;" 2>/dev/null
```

4. **Matter-scoped document stats via API** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  http://localhost:8000/api/v1/documents/stats | python3 -m json.tool
```

### Step 4 — Data Integrity

Run these 4 queries to check cross-store consistency. These can run in parallel:

1. **PG chunks vs Qdrant points:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -t -c "SELECT coalesce(sum(chunk_count),0) FROM documents;"
```
Compare with the Qdrant `points_count` from Step 3. If delta > 1%, flag YELLOW. If delta > 10%, flag RED.

2. **PG documents vs Neo4j Document nodes:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -t -c "SELECT count(*) FROM documents;"
```
```bash
docker compose exec -T neo4j cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-changeme}" \
  "MATCH (d:Document) RETURN count(d) AS count;" 2>/dev/null
```

3. **PG entities vs Neo4j Entity nodes:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -t -c "SELECT coalesce(sum(entity_count),0) FROM documents;"
```
```bash
docker compose exec -T neo4j cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-changeme}" \
  "MATCH (e:Entity) RETURN count(e) AS count;" 2>/dev/null
```
Note: Neo4j count is typically lower because entity resolution merges duplicates. This is expected.

4. **Stuck jobs (processing for > 30 minutes):**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT id, filename, status, stage, updated_at,
       extract(epoch from (NOW() - updated_at))/60 AS minutes_stuck
FROM jobs
WHERE status IN ('processing','uploading','parsing','chunking','embedding','extracting','indexing')
  AND updated_at < NOW() - INTERVAL '30 minutes'
ORDER BY updated_at
LIMIT 10;
"
```

### Step 5 — Ingestion Pipeline (run in parallel)

Run these 6 commands in parallel:

1. **Job status breakdown:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT status, count(*) AS count FROM jobs GROUP BY status ORDER BY count DESC;
"
```

2. **Active jobs with progress:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT filename, status, stage, task_type,
       created_at, updated_at,
       extract(epoch from (NOW() - created_at))/60 AS age_minutes
FROM jobs
WHERE status IN ('pending','processing','uploading','parsing','chunking','embedding','extracting','indexing')
ORDER BY created_at DESC
LIMIT 20;
"
```

3. **Recent failures (last 10):**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT filename, error_category, left(error, 120) AS error_preview, stage, updated_at
FROM jobs
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 10;
"
```

4. **Pipeline throughput** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  http://localhost:8000/api/v1/admin/pipeline/throughput | python3 -m json.tool
```

5. **Bulk import status:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT id, source_name, total_files, processed_count, failed_count, status, created_at
FROM bulk_import_jobs
ORDER BY created_at DESC
LIMIT 5;
" 2>/dev/null || echo "No bulk_import_jobs table or no data"
```

6. **Failure analysis** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  "http://localhost:8000/api/v1/admin/pipeline/failure-analysis?hours=168" | python3 -m json.tool
```

### Step 6 — Queue & Workers (run in parallel)

Run these 4 commands in parallel:

1. **Celery overview via API** (auth — skip if API_DOWN):
```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000001" \
  http://localhost:8000/api/v1/admin/operations/celery | python3 -m json.tool
```

2. **RabbitMQ queue depths** (skip if RabbitMQ not running):
```bash
curl -sf -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" http://localhost:15672/api/queues/nexus | python3 -c "
import sys,json
queues = json.load(sys.stdin)
for q in queues:
    print(f\"{q['name']}: ready={q.get('messages_ready',0)}, unacked={q.get('messages_unacknowledged',0)}, consumers={q.get('consumers',0)}, publish_rate={q.get('message_stats',{}).get('publish_details',{}).get('rate',0)}/s\")
" 2>/dev/null || echo "RabbitMQ not available (Redis broker mode)"
```

3. **RabbitMQ overview:**
```bash
curl -sf -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" http://localhost:15672/api/overview | python3 -c "
import sys,json
d=json.load(sys.stdin)
q=d.get('queue_totals',{})
obj=d.get('object_totals',{})
print(f\"Messages ready: {q.get('messages_ready',0)}\")
print(f\"Messages unacked: {q.get('messages_unacknowledged',0)}\")
print(f\"Connections: {obj.get('connections',0)}\")
print(f\"Queues: {obj.get('queues',0)}\")
print(f\"Consumers: {obj.get('consumers',0)}\")
print(f\"RabbitMQ version: {d.get('rabbitmq_version','?')}\")
print(f\"Erlang version: {d.get('erlang_version','?')}\")
" 2>/dev/null || echo "RabbitMQ not available"
```

4. **Running external scripts:**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT name, script_name, status, processed, failed, total,
       extract(epoch from (NOW() - updated_at))/60 AS minutes_since_update,
       created_at
FROM external_tasks
WHERE status IN ('running', 'stale')
ORDER BY created_at DESC
LIMIT 10;
" 2>/dev/null || echo "No external_tasks table or no data"
```

#### Worker Efficiency Rating

After collecting data from Steps 5 and 6, compute the worker efficiency rating:

**Inputs needed:**
- `pending_jobs`: count of jobs with status `pending` (from Step 5.1)
- `queue_ready`: total `messages_ready` across all RabbitMQ queues (from Step 6.2/6.3), or pending job count as proxy if Redis broker
- `active_tasks`: total active tasks across all workers (from Step 6.1)
- `worker_count`: number of online workers (from Step 6.1)
- `total_concurrency`: sum of concurrency across all workers (from Step 6.1)
- `jobs_per_minute`: throughput metric (from Step 5.4)
- `avg_duration`: average job duration (from Step 5.4)

**Rating logic:**
- **OVER-PROVISIONED**: `active_tasks == 0 AND pending_jobs == 0 AND queue_ready == 0` and this has been the case (no jobs completed recently either). Workers are idle — consider reducing replicas or concurrency.
- **RIGHT-SIZED**: `pending_jobs + queue_ready < 2 * total_concurrency` and workers have some active tasks. Pipeline is keeping up.
- **UNDER-PROVISIONED**: `pending_jobs + queue_ready > 5 * total_concurrency`, OR avg wait time (pending jobs / jobs_per_minute) > 5 minutes. Pipeline is falling behind — increase workers or concurrency.
- **BOTTLENECKED**: One queue has > 80% of all pending messages while others are empty. A specific queue needs dedicated workers (e.g., `ner` queue for NER extraction).

Include the rating and a specific recommendation in the report.

### Step 7 — Error State Analysis

Run these 3 queries (can run in parallel):

1. **Error category distribution (last 7 days):**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT coalesce(error_category, 'UNKNOWN') AS category,
       count(*) AS count,
       round(count(*) * 100.0 / nullif(sum(count(*)) OVER (), 0), 1) AS pct
FROM jobs
WHERE status = 'failed'
  AND updated_at > NOW() - INTERVAL '7 days'
GROUP BY category
ORDER BY count DESC;
"
```

2. **Sample errors per category (most recent per category):**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT error_category, filename, left(error, 300) AS error_detail, stage, updated_at
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY coalesce(error_category,'UNKNOWN') ORDER BY updated_at DESC) AS rn
    FROM jobs
    WHERE status = 'failed'
      AND updated_at > NOW() - INTERVAL '7 days'
      AND error IS NOT NULL
) sub
WHERE rn <= 3
ORDER BY error_category, updated_at DESC;
"
```

3. **Failure rate trend (hourly, last 24h):**
```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "
SELECT date_trunc('hour', updated_at) AS hour,
       count(*) FILTER (WHERE status = 'failed') AS failed,
       count(*) FILTER (WHERE status IN ('complete','completed')) AS completed,
       CASE WHEN count(*) > 0
            THEN round(count(*) FILTER (WHERE status = 'failed') * 100.0 / count(*), 1)
            ELSE 0 END AS failure_pct
FROM jobs
WHERE updated_at > NOW() - INTERVAL '24 hours'
  AND status IN ('failed','complete','completed')
GROUP BY hour
ORDER BY hour;
"
```

#### Error State Rating

After collecting the error data, compute the error state rating:

**Inputs needed:**
- `total_failed_24h`: failed jobs in last 24 hours
- `total_completed_24h`: completed jobs in last 24 hours
- `failure_rate`: `total_failed_24h / (total_failed_24h + total_completed_24h)`
- `dominant_category`: the error category with highest count
- `dominant_pct`: percentage of failures in the dominant category
- `trend`: whether failure rate in last 3 hours is higher than the prior 21 hours
- `sampled_errors`: the error samples from query 2

**Rating logic:**
- **CLEAN**: 0 failures in last 24h. No action needed.
- **NOMINAL**: Failure rate < 5%, no single category > 50%. Monitor only.
- **DEGRADED**: Failure rate 5-20%, OR one category > 50% of failures. Investigate the dominant category.
- **CRITICAL**: Failure rate > 20%, OR trend is increasing (last 3h worse than prior 21h), OR a previously unseen error category appeared. Immediate investigation needed.

**For DEGRADED and CRITICAL ratings, analyze the sampled errors and provide:**
1. The dominant failure category with representative error text
2. Whether errors are **transient** (retryable — e.g., TIMEOUT, NETWORK) or **systemic** (need code/config fix — e.g., PARSE_ERROR, VALIDATION, OOM)
3. Which pipeline stage failures concentrate in (e.g., embedding, parsing)
4. Specific recommendations (e.g., "TIMEOUT errors on embedding stage — check Ollama/TEI container health and increase `LLM_TIMEOUT`")

### Step 8 — LLM & Embedding (only if `$ARGUMENTS` contains "deep")

**Skip this step unless the user passed "deep" as an argument (e.g., `/system-status deep`).**

This is expensive — makes real LLM completion and embedding API calls.

```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/health/deep | python3 -m json.tool
```

Report the LLM provider, model, response latency, embedding provider, dimensions, and Qdrant collection health.

### Step 9 — Compile Report

Present all findings in this format:

```
# NEXUS Local System Status — <timestamp>

## Overall Status: GREEN / YELLOW / RED

Criteria:
- GREEN: All 6+ core services healthy, no stuck jobs, disk < 70%, no failures in last hour, workers right-sized, error state CLEAN or NOMINAL
- YELLOW: Non-critical service issue, disk 70-85%, some recent failures, queue backlog > 100, stuck jobs, worker efficiency issue, error state DEGRADED
- RED: Core service down (API, Postgres, Qdrant, Neo4j), disk > 85%, data integrity mismatch > 10%, all workers offline, error state CRITICAL

---

## 1. Service Health
| Service | Docker Status | API Health | Latency | Notes |
|---------|--------------|------------|---------|-------|
| PostgreSQL | ... | ... | ... | ... |
| Qdrant | ... | ... | ... | ... |
| Neo4j | ... | ... | ... | ... |
| Redis | ... | ... | ... | ... |
| MinIO | ... | ... | ... | ... |
| RabbitMQ | ... | ... | ... | ... |
| API | ... | — | — | ... |
| Celery Worker(s) | ... | — | — | ... |

## 2. Resource Usage
| Resource | Used | Total | % | Assessment |
|----------|------|-------|---|------------|
| CPU | ... | ... | ... | ... |
| Memory | ... | ... | ... | ... |
| Disk (/) | ... | ... | ... | ... |
| PG Database | ... | — | — | ... |
| Qdrant (nexus_text) | ... pts | — | — | ... |
| Qdrant (nexus_visual) | ... pts | — | — | ... |

## 3. Data Inventory
| Store | Metric | Count |
|-------|--------|-------|
| PostgreSQL | Documents | ... |
| PostgreSQL | Pages | ... |
| PostgreSQL | Chunks | ... |
| PostgreSQL | Entities | ... |
| PostgreSQL | File Size | ... |
| Qdrant | nexus_text points | ... |
| Qdrant | nexus_visual points | ... |
| Neo4j | Nodes by label | ... per label ... |
| Neo4j | Relationships by type | ... per type ... |

## 4. Data Integrity
| Check | Store A | Count A | Store B | Count B | Delta | Status |
|-------|---------|---------|---------|---------|-------|--------|
| Chunks vs Qdrant | PG chunk_count | ... | Qdrant points | ... | ... | OK/WARN/FAIL |
| Docs vs Neo4j | PG documents | ... | Neo4j :Document | ... | ... | OK/WARN/FAIL |
| Entities vs Neo4j | PG entity_count | ... | Neo4j :Entity | ... | ... | OK/INFO |
| Stuck jobs (>30m) | — | — | — | — | ... | OK/WARN |

## 5. Ingestion Pipeline

### Job Status Breakdown
| Status | Count |
|--------|-------|
(per status row)

### Active Jobs (top 20)
| Filename | Status | Stage | Task Type | Age (min) |
|----------|--------|-------|-----------|-----------|
(active job rows, or "None — pipeline idle")

### Recent Failures (last 10)
| Filename | Category | Error | Stage | When |
|----------|----------|-------|-------|------|
(failure rows, or "None — clean run")

### Throughput
- Jobs/min: ...
- Jobs last hour: ...
- Avg duration: ...s

### Bulk Imports
| Source | Total | Processed | Failed | Status |
|--------|-------|-----------|--------|--------|
(bulk import rows, or "None")

## 6. Queue & Workers

### Celery Workers
| Worker | Status | Active Tasks | Concurrency | Queues | Uptime |
|--------|--------|-------------|-------------|--------|--------|
(worker rows, or "No workers online")

### Queue Depths
| Queue | Ready | Unacked | Consumers | Publish Rate |
|-------|-------|---------|-----------|-------------|
| default | ... | ... | ... | ... |
| bulk | ... | ... | ... | ... |
| ner | ... | ... | ... | ... |
| background | ... | ... | ... | ... |

### Worker Efficiency: OVER-PROVISIONED / RIGHT-SIZED / UNDER-PROVISIONED / BOTTLENECKED
(Explanation of rating with key metrics and specific recommendation)

### External Scripts
| Name | Script | Progress | Failed | Status | Last Update |
|------|--------|----------|--------|--------|-------------|
(running scripts, or "None")

## 7. Error State: CLEAN / NOMINAL / DEGRADED / CRITICAL

### Error Distribution (last 7 days)
| Category | Count | % |
|----------|-------|---|
(category rows)

### Failure Trend (last 24h)
| Hour | Failed | Completed | Failure % |
|------|--------|-----------|-----------|
(hourly rows — show last 6 hours minimum)

### Error Samples & Diagnosis
(For DEGRADED/CRITICAL: sampled errors with analysis of whether transient/systemic, which stage, and specific fix recommendations)

## 8. LLM & Embedding (only if deep check was run)
| Component | Provider | Model | Status | Latency |
|-----------|----------|-------|--------|---------|
| LLM | ... | ... | ... | ...ms |
| Embedding | ... | ... | ... | ...ms |

## Recommendations
(Numbered action items ordered by priority. Derived from all sections above. Examples:)
1. [HIGH] ...
2. [MEDIUM] ...
3. [LOW] ...
```

## Known Issues (do not re-flag)

These are pre-existing and expected in local dev:

- `ollama.discover.failed` — No Ollama server running unless explicitly started. Not required for cloud LLM providers.
- `FLOWER_USER`/`FLOWER_PASSWORD` not set — Flower env vars are optional in dev.
- GPU metrics unavailable on macOS — `/proc/stat` and `nvidia-smi` not available; system metrics will show 0% CPU and partial memory info. This is expected.
- Neo4j APOC/GDS plugin warnings on first start — cosmetic.
- RabbitMQ may not be running if using Redis as Celery broker (default for `make dev`). If RabbitMQ is not available, skip RabbitMQ checks and note "Redis broker mode" in the queue section.
- `bulk_import_jobs` or `external_tasks` tables may not exist if those migrations haven't run — handle gracefully.

## Notes

- **Maximize parallelism.** Steps 1, 2, 3, 5, 6, and 7 each contain independent commands that MUST run in parallel (multiple Bash calls in one message).
- **API startup takes 45-90s.** If `make dev` was just started, health check failure may be transient. Wait and retry.
- **The `X-Matter-ID` header** is required for some admin endpoints. Use `00000000-0000-0000-0000-000000000001`.
- **The `$ARGUMENTS` variable**: if the user passes "deep" (e.g., `/system-status deep`), run Step 8 for LLM/embedding health. Otherwise skip it.
- **When the API is down**, produce 80%+ of the report via direct Docker/CLI queries. Only API-exclusive data (throughput, failure-analysis API, Celery overview, container details) will be missing.
- **Error state analysis** is the most valuable section during active ingestion. Always include it, even when the API is down.
- **Worker efficiency rating** should account for the current workload phase: during active bulk ingestion, workers being fully utilized is expected (RIGHT-SIZED), not a problem.
