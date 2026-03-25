#!/bin/bash
# Startup script for NER worker spot VMs.
# Installed via instance metadata; runs on VM boot.
# Pulls the NEXUS Docker image from GCR and starts a Celery worker
# consuming only the 'ner' queue (GLiNER entity extraction).
#
# Required instance metadata keys:
#   nexus-main-vm-ip  — Internal IP of nexus-gpu (services host)
#   nexus-pg-pass     — PostgreSQL password
#   nexus-rabbitmq-pass — RabbitMQ password
#   nexus-neo4j-pass  — Neo4j password
#
# Usage:
#   gcloud compute instances create nexus-ner-1 \
#     --metadata-from-file=startup-script=scripts/ner_worker_startup.sh \
#     --metadata=nexus-main-vm-ip=10.138.0.XX,nexus-pg-pass=xxx,...

set -euo pipefail

LOGFILE="/var/log/nexus-ner-worker.log"
exec > >(tee -a "$LOGFILE") 2>&1

echo "[$(date -Is)] NER worker startup: begin"

# ── Fetch metadata ──────────────────────────────────────────────
metadata_url="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
MAIN_VM_IP=$(curl -sf -H "Metadata-Flavor: Google" "$metadata_url/nexus-main-vm-ip")
PG_PASS=$(curl -sf -H "Metadata-Flavor: Google" "$metadata_url/nexus-pg-pass")
RABBITMQ_PASS=$(curl -sf -H "Metadata-Flavor: Google" "$metadata_url/nexus-rabbitmq-pass")
NEO4J_PASS=$(curl -sf -H "Metadata-Flavor: Google" "$metadata_url/nexus-neo4j-pass")

echo "[$(date -Is)] Main VM IP: $MAIN_VM_IP"

# ── Install Docker ──────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[$(date -Is)] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# ── Authenticate to GCR ────────────────────────────────────────
echo "[$(date -Is)] Configuring GCR auth..."
gcloud auth configure-docker gcr.io --quiet 2>/dev/null || true

# ── Pull image ──────────────────────────────────────────────────
IMAGE="gcr.io/vault-ai-487703/nexus-api:latest"
echo "[$(date -Is)] Pulling $IMAGE..."
docker pull "$IMAGE"

# ── Start NER worker ────────────────────────────────────────────
echo "[$(date -Is)] Starting NER worker (4 prefork processes)..."
docker run -d \
    --restart=unless-stopped \
    --name=nexus-ner-worker \
    --memory=14g \
    -e DATABASE_URL="postgresql+asyncpg://nexus:${PG_PASS}@${MAIN_VM_IP}:5432/nexus" \
    -e SYNC_DATABASE_URL="postgresql://nexus:${PG_PASS}@${MAIN_VM_IP}:5432/nexus" \
    -e CELERY_BROKER_URL="amqp://nexus:${RABBITMQ_PASS}@${MAIN_VM_IP}:5672/nexus" \
    -e CELERY_RESULT_BACKEND="redis://${MAIN_VM_IP}:6379/0" \
    -e REDIS_URL="redis://${MAIN_VM_IP}:6379/0" \
    -e QDRANT_URL="http://${MAIN_VM_IP}:6333" \
    -e NEO4J_URI="bolt://${MAIN_VM_IP}:7687" \
    -e NEO4J_USER="neo4j" \
    -e NEO4J_PASSWORD="${NEO4J_PASS}" \
    -e GLINER_MODEL="urchade/gliner_multi_pii-v1" \
    "$IMAGE" \
    celery -A workers.celery_app worker \
        -l info \
        -Q ner \
        -c 4 \
        -P prefork \
        --max-tasks-per-child=50

echo "[$(date -Is)] NER worker startup: done"
