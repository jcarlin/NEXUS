#!/bin/bash
# Startup script for MIG satellite worker VMs.
#
# Runs on each satellite VM boot:
# 1. Install Docker
# 2. Authenticate to GCR
# 3. Pull nexus-api image
# 4. Read config from instance metadata
# 5. Start 2 Celery worker containers connecting to the main VM
#
# Config is passed via instance metadata (set in the instance template).

set -euo pipefail

METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
METADATA_HEADER="Metadata-Flavor: Google"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Fetch config from instance metadata ─────────────────────────
log "Fetching config from instance metadata..."
MAIN_VM_IP=$(curl -sf "$METADATA_URL/nexus-main-vm-ip" -H "$METADATA_HEADER")
PG_PASS=$(curl -sf "$METADATA_URL/nexus-pg-pass" -H "$METADATA_HEADER")
RABBITMQ_PASS=$(curl -sf "$METADATA_URL/nexus-rabbitmq-pass" -H "$METADATA_HEADER")
NEO4J_PASS=$(curl -sf "$METADATA_URL/nexus-neo4j-pass" -H "$METADATA_HEADER")
GEMINI_API_KEY=$(curl -sf "$METADATA_URL/nexus-gemini-key" -H "$METADATA_HEADER")
MINIO_ACCESS_KEY=$(curl -sf "$METADATA_URL/nexus-minio-access-key" -H "$METADATA_HEADER" || echo "minioadmin")
MINIO_SECRET_KEY=$(curl -sf "$METADATA_URL/nexus-minio-secret-key" -H "$METADATA_HEADER" || echo "minioadmin")

# Optional: OCR mode (defaults to "false" for max speed on text-based corpus)
DOCLING_OCR=$(curl -sf "$METADATA_URL/nexus-docling-ocr" -H "$METADATA_HEADER" || echo "false")

log "Main VM: $MAIN_VM_IP"
log "OCR mode: $DOCLING_OCR"

# ── Install Docker ──────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    apt-get update -qq && apt-get install -y -qq docker.io
fi

# ── Authenticate to GCR ────────────────────────────────────────
log "Authenticating to GCR..."
gcloud auth configure-docker gcr.io --quiet

# ── Pull image ──────────────────────────────────────────────────
IMAGE="gcr.io/vault-ai-487703/nexus-api:latest"
log "Pulling $IMAGE..."
docker pull "$IMAGE"

# ── Start worker containers ────────────────────────────────────
HOSTNAME=$(hostname)

for i in 1 2; do
    WORKER_NAME="worker-${HOSTNAME}-${i}"
    log "Starting $WORKER_NAME..."

    docker run -d \
        --name "$WORKER_NAME" \
        --restart=unless-stopped \
        -e POSTGRES_URL="postgresql+asyncpg://nexus:${PG_PASS}@${MAIN_VM_IP}:5432/nexus" \
        -e POSTGRES_URL_SYNC="postgresql://nexus:${PG_PASS}@${MAIN_VM_IP}:5432/nexus" \
        -e REDIS_URL="redis://${MAIN_VM_IP}:6379/0" \
        -e CELERY_BROKER_URL="amqp://nexus:${RABBITMQ_PASS}@${MAIN_VM_IP}:5672/nexus" \
        -e QDRANT_URL="http://${MAIN_VM_IP}:6333" \
        -e NEO4J_URI="bolt://${MAIN_VM_IP}:7687" \
        -e NEO4J_PASSWORD="${NEO4J_PASS}" \
        -e MINIO_ENDPOINT="${MAIN_VM_IP}:9000" \
        -e MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY}" \
        -e MINIO_SECRET_KEY="${MINIO_SECRET_KEY}" \
        -e OMP_NUM_THREADS=4 \
        -e MKL_NUM_THREADS=4 \
        -e ENABLE_DOCLING_OCR="${DOCLING_OCR}" \
        -e ENABLE_SPARSE_EMBEDDINGS=true \
        -e DEFER_NER_TO_QUEUE=true \
        -e EMBEDDING_PROVIDER=gemini \
        -e GEMINI_API_KEY="${GEMINI_API_KEY}" \
        "$IMAGE" \
        celery -A workers.celery_app worker \
            -Q default,bulk,background \
            -n "${WORKER_NAME}@%h" \
            -l info -c 1 \
            --pool=prefork \
            --max-tasks-per-child=100 \
            --without-heartbeat

    log "$WORKER_NAME started"
done

log "Satellite worker setup complete. Workers connecting to $MAIN_VM_IP"
