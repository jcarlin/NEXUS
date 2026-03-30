#!/bin/bash
# Create a Managed Instance Group (MIG) for horizontal ingest worker scaling.
#
# Components:
#   1. Instance template (n2-standard-8, preemptible, startup script)
#   2. MIG (starts at size=0)
#   3. Autoscaler (scales on custom queue depth metric, 0-12 VMs)
#   4. Firewall rule for internal VPC access (idempotent)
#
# Prerequisites:
#   1. Docker image pushed to GCR (see push_worker_image.sh)
#   2. Queue metric exporter running on main VM
#   3. Main VM internal IP known
#
# Usage:
#   bash scripts/infra/create_worker_mig.sh

set -euo pipefail

PROJECT="vault-ai-487703"
ZONE="us-west1-a"
MACHINE_TYPE="n2-standard-8"  # 8 vCPU, 32GB RAM — fits 2 prefork workers comfortably
TEMPLATE_NAME="nexus-ingest-worker"
MIG_NAME="nexus-ingest-mig"
MAX_REPLICAS=12

echo "=== NEXUS Ingest Worker MIG Setup ==="
echo "Machine type: $MACHINE_TYPE"
echo "Max replicas: $MAX_REPLICAS"
echo ""

# ── Detect main VM internal IP ──────────────────────────────────
MAIN_VM_IP=$(gcloud compute instances describe nexus-ingest \
    --zone="$ZONE" --project="$PROJECT" \
    --format='get(networkInterfaces[0].networkIP)' 2>/dev/null)

if [ -z "$MAIN_VM_IP" ]; then
    echo "ERROR: Could not detect nexus-ingest internal IP. Is the VM running?"
    exit 1
fi
echo "Main VM internal IP: $MAIN_VM_IP"

# ── Prompt for credentials ──────────────────────────────────────
read -rsp "PostgreSQL password: " PG_PASS; echo
read -rsp "RabbitMQ password: " RABBITMQ_PASS; echo
read -rsp "Neo4j password: " NEO4J_PASS; echo
read -rsp "Gemini API key: " GEMINI_KEY; echo
read -rp  "MinIO access key [minioadmin]: " MINIO_AK; MINIO_AK="${MINIO_AK:-minioadmin}"; echo
read -rsp "MinIO secret key [minioadmin]: " MINIO_SK; MINIO_SK="${MINIO_SK:-minioadmin}"; echo
read -rp  "Docling OCR mode [false]: " DOCLING_OCR; DOCLING_OCR="${DOCLING_OCR:-false}"; echo

# ── Create firewall rule (idempotent) ───────────────────────────
if ! gcloud compute firewall-rules describe nexus-internal-services --project="$PROJECT" &>/dev/null; then
    echo "Creating firewall rule for internal services..."
    gcloud compute firewall-rules create nexus-internal-services \
        --project="$PROJECT" \
        --allow=tcp:5432,tcp:5672,tcp:6333,tcp:6379,tcp:7687,tcp:9000 \
        --source-tags=nexus-internal \
        --target-tags=nexus-internal \
        --network=default \
        --description="Allow worker VMs to reach nexus-ingest services"
else
    echo "Firewall rule nexus-internal-services already exists."
fi

# ── Ensure nexus-ingest has the tag ─────────────────────────────
EXISTING_TAGS=$(gcloud compute instances describe nexus-ingest \
    --zone="$ZONE" --project="$PROJECT" \
    --format='value(tags.items)' 2>/dev/null || echo "")

if [[ "$EXISTING_TAGS" != *"nexus-internal"* ]]; then
    echo "Adding nexus-internal tag to nexus-ingest..."
    gcloud compute instances add-tags nexus-ingest \
        --zone="$ZONE" --project="$PROJECT" \
        --tags=nexus-internal
fi

# ── Delete old template if it exists (templates are immutable) ──
if gcloud compute instance-templates describe "$TEMPLATE_NAME" --project="$PROJECT" &>/dev/null; then
    echo "Deleting old instance template $TEMPLATE_NAME..."
    gcloud compute instance-templates delete "$TEMPLATE_NAME" \
        --project="$PROJECT" --quiet
fi

# ── Create instance template ────────────────────────────────────
echo "Creating instance template: $TEMPLATE_NAME..."
gcloud compute instance-templates create "$TEMPLATE_NAME" \
    --project="$PROJECT" \
    --machine-type="$MACHINE_TYPE" \
    --provisioning-model=SPOT \
    --instance-termination-action=STOP \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --scopes=storage-ro,logging-write,monitoring-write \
    --metadata="nexus-main-vm-ip=$MAIN_VM_IP,nexus-pg-pass=$PG_PASS,nexus-rabbitmq-pass=$RABBITMQ_PASS,nexus-neo4j-pass=$NEO4J_PASS,nexus-gemini-key=$GEMINI_KEY,nexus-minio-access-key=$MINIO_AK,nexus-minio-secret-key=$MINIO_SK,nexus-docling-ocr=$DOCLING_OCR" \
    --metadata-from-file="startup-script=scripts/infra/ingest_worker_startup.sh" \
    --tags=nexus-internal

# ── Create MIG ──────────────────────────────────────────────────
if ! gcloud compute instance-groups managed describe "$MIG_NAME" \
    --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "Creating MIG: $MIG_NAME (size=0)..."
    gcloud compute instance-groups managed create "$MIG_NAME" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --template="$TEMPLATE_NAME" \
        --size=0
else
    echo "MIG $MIG_NAME already exists. Updating template..."
    gcloud compute instance-groups managed set-instance-template "$MIG_NAME" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --template="$TEMPLATE_NAME"
fi

# ── Configure autoscaler ────────────────────────────────────────
echo "Configuring autoscaler..."
gcloud compute instance-groups managed set-autoscaling "$MIG_NAME" \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --min-num-replicas=0 \
    --max-num-replicas="$MAX_REPLICAS" \
    --update-stackdriver-metric="custom.googleapis.com/rabbitmq/queue_depth/bulk" \
    --stackdriver-metric-utilization-target=50 \
    --stackdriver-metric-utilization-target-type=gauge \
    --cool-down-period=300 \
    --scale-in-control-max-scaled-in-replicas=2 \
    --scale-in-control-time-window=600

echo ""
echo "=== MIG Setup Complete ==="
echo "MIG: $MIG_NAME (size=0, max=$MAX_REPLICAS)"
echo "Autoscaler: scales on queue_depth/bulk > 50 per instance"
echo ""
echo "Commands:"
echo "  Smoke test:   gcloud compute instance-groups managed resize $MIG_NAME --size=1 --zone=$ZONE --project=$PROJECT"
echo "  Scale down:   gcloud compute instance-groups managed resize $MIG_NAME --size=0 --zone=$ZONE --project=$PROJECT"
echo "  Status:       gcloud compute instance-groups managed list-instances $MIG_NAME --zone=$ZONE --project=$PROJECT"
echo "  Teardown:     bash scripts/infra/teardown_worker_mig.sh"
