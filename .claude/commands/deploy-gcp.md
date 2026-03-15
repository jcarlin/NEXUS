# Deploy to GCP

Deploy the latest `origin/main` to the GCP VM. Handles VM start, code pull, Docker rebuild, migration, and health checks.

**Prerequisites:** Code must already be pushed to `origin/main`. This command does NOT push for you.

## Constants

- **GCP Project:** `vault-ai-487703`
- **VM:** `nexus-demo`
- **Zone:** `us-central1-a`
- **Compose files:** `docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml`
- **Frontend:** `https://nexus-alpha-swart.vercel.app` (deployed separately via Vercel)

## Steps

Run every `gcloud` command with `--project=vault-ai-487703` to avoid targeting the wrong GCP project.

### Step 1 — Check VM status and get external IP

```bash
gcloud compute instances describe nexus-demo \
  --zone=us-central1-a \
  --project=vault-ai-487703 \
  --format="get(status,networkInterfaces[0].accessConfigs[0].natIP)"
```

Save the external IP from the output — it changes on every VM start (no static IP reserved).

### Step 2 — Start VM if stopped

If the status from Step 1 is `TERMINATED` or `STOPPED`:

```bash
gcloud compute instances start nexus-demo \
  --zone=us-central1-a \
  --project=vault-ai-487703
```

Then get the new external IP:

```bash
gcloud compute instances describe nexus-demo \
  --zone=us-central1-a \
  --project=vault-ai-487703 \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

Then wait for SSH to become available. Retry up to 12 times, 10 seconds apart:

```bash
gcloud compute ssh nexus-demo \
  --zone=us-central1-a \
  --project=vault-ai-487703 \
  --ssh-flag="-o ConnectTimeout=5" \
  --command="echo 'SSH ready'"
```

If SSH is not available after 12 retries (2 minutes), report the failure and stop.

If the VM is already `RUNNING`, skip straight to Step 3.

### Step 3 — Deploy via SSH

Run this **single** SSH command. It mirrors `.github/workflows/deploy.yml` exactly:

```bash
gcloud compute ssh nexus-demo \
  --zone=us-central1-a \
  --project=vault-ai-487703 \
  --ssh-flag="-o ConnectTimeout=5" \
  --command='set -euo pipefail
cd ~/nexus
COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml"

# Pull latest code
git fetch origin main
git checkout origin/main

# Rebuild and restart API + worker only
$COMPOSE up -d --build api worker

# Run any pending migrations
$COMPOSE exec -T api alembic upgrade head

# Wait for health check (60 retries x 3s = 180s max)
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo "Health check passed"
    exit 0
  fi
  sleep 3
done
echo "Health check failed after 180s"
$COMPOSE logs --tail=50 api
exit 1'
```

### Step 4 — Check if `vercel.json` needs an IP update

If the VM was started (Step 2) or the IP differs from what's in `frontend/vercel.json`, update the rewrite destination IP and tell the user to push + redeploy Vercel.

### Step 5 — External health check

Verify the API is reachable from outside the VM using the IP from Step 1/2:

```bash
curl -sf http://<EXTERNAL_IP>:8000/api/v1/health
```

If this fails, warn the user (firewall rules may need attention) but don't treat it as a deploy failure — the internal health check in Step 3 already passed.

### Step 6 — Report

Print a summary using the actual external IP:

```
Deploy complete!

  API:      http://<EXTERNAL_IP>:8000
  Health:   http://<EXTERNAL_IP>:8000/api/v1/health
  Docs:     http://<EXTERNAL_IP>:8000/docs
  Frontend: https://nexus-alpha-swart.vercel.app

Cost reminder: VM costs ~$60-80/mo running. Stop it when done:
  gcloud compute instances stop nexus-demo --zone=us-central1-a --project=vault-ai-487703
```

## Notes

- **Only `api` and `worker` are rebuilt.** Infrastructure services (postgres, redis, qdrant, neo4j, minio, caddy) have `restart: unless-stopped` and come up automatically when the VM starts.
- **Frontend is NOT deployed here.** Vercel deploys automatically on push to main.
- **API startup takes ~45s normally**, but cold boots (first start after image rebuild, or GLiNER model download) can take up to 2-3 minutes. The 180s health check timeout accounts for this.
- **Ephemeral IP:** The VM has no static IP. The external IP changes on every start. When it changes, `frontend/vercel.json` must be updated and pushed so Vercel routes to the new IP.
- **If deploy fails**, check logs: `gcloud compute ssh nexus-demo --zone=us-central1-a --project=vault-ai-487703 --command="cd ~/nexus && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml logs --tail=100 api"`
