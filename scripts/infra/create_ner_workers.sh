#!/bin/bash
# Create spot NER worker VMs for distributed GLiNER entity extraction.
#
# These VMs connect to the nexus-gpu main VM's RabbitMQ, PostgreSQL, Qdrant,
# and Neo4j services via internal VPC networking. Each runs 4 Celery prefork
# processes consuming the 'ner' queue.
#
# Prerequisites:
#   1. Docker image pushed to GCR:
#      docker tag nexus-api gcr.io/vault-ai-487703/nexus-api:latest
#      docker push gcr.io/vault-ai-487703/nexus-api:latest
#   2. Firewall rule for internal services (created below if missing)
#   3. nexus-gpu internal IP known (auto-detected below)
#
# Usage:
#   bash scripts/infra/create_ner_workers.sh [NUM_WORKERS]
#   bash scripts/infra/create_ner_workers.sh 6

set -euo pipefail

NUM_WORKERS="${1:-6}"
PROJECT="vault-ai-487703"
ZONE="us-west1-a"
MACHINE_TYPE="n1-standard-4"  # 4 vCPU, 15GB RAM — fits 4 GLiNER processes (~600MB each)
TEMPLATE_NAME="nexus-ner-worker"

echo "=== NEXUS NER Worker Setup ==="
echo "Workers: $NUM_WORKERS"
echo "Machine type: $MACHINE_TYPE"
echo "Zone: $ZONE"
echo ""

# ── Detect main VM internal IP ──────────────────────────────────
MAIN_VM_IP=$(gcloud compute instances describe nexus-gpu \
    --zone="$ZONE" --project="$PROJECT" \
    --format='get(networkInterfaces[0].networkIP)' 2>/dev/null)

if [ -z "$MAIN_VM_IP" ]; then
    echo "ERROR: Could not detect nexus-gpu internal IP. Is the VM running?"
    exit 1
fi
echo "Main VM internal IP: $MAIN_VM_IP"

# ── Prompt for credentials ──────────────────────────────────────
read -rsp "PostgreSQL password: " PG_PASS; echo
read -rsp "RabbitMQ password: " RABBITMQ_PASS; echo
read -rsp "Neo4j password: " NEO4J_PASS; echo

# ── Create firewall rule (idempotent) ───────────────────────────
if ! gcloud compute firewall-rules describe nexus-internal-services --project="$PROJECT" &>/dev/null; then
    echo "Creating firewall rule for internal services..."
    gcloud compute firewall-rules create nexus-internal-services \
        --project="$PROJECT" \
        --allow=tcp:5432,tcp:5672,tcp:6333,tcp:6379,tcp:7687 \
        --source-tags=nexus-internal \
        --target-tags=nexus-internal \
        --network=default \
        --description="Allow NER workers to reach nexus-gpu services"
else
    echo "Firewall rule nexus-internal-services already exists."
fi

# ── Ensure nexus-gpu has the tag ────────────────────────────────
EXISTING_TAGS=$(gcloud compute instances describe nexus-gpu \
    --zone="$ZONE" --project="$PROJECT" \
    --format='value(tags.items)' 2>/dev/null || echo "")

if [[ "$EXISTING_TAGS" != *"nexus-internal"* ]]; then
    echo "Adding nexus-internal tag to nexus-gpu..."
    gcloud compute instances add-tags nexus-gpu \
        --zone="$ZONE" --project="$PROJECT" \
        --tags=nexus-internal
fi

# ── Create instance template (idempotent) ───────────────────────
if ! gcloud compute instance-templates describe "$TEMPLATE_NAME" --project="$PROJECT" &>/dev/null; then
    echo "Creating instance template: $TEMPLATE_NAME..."
    gcloud compute instance-templates create "$TEMPLATE_NAME" \
        --project="$PROJECT" \
        --machine-type="$MACHINE_TYPE" \
        --preemptible \
        --boot-disk-size=30GB \
        --boot-disk-type=pd-standard \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --scopes=storage-ro,logging-write \
        --metadata="nexus-main-vm-ip=$MAIN_VM_IP,nexus-pg-pass=$PG_PASS,nexus-rabbitmq-pass=$RABBITMQ_PASS,nexus-neo4j-pass=$NEO4J_PASS" \
        --metadata-from-file="startup-script=scripts/ner_worker_startup.sh" \
        --tags=nexus-internal
else
    echo "Instance template $TEMPLATE_NAME already exists."
fi

# ── Create worker VMs ───────────────────────────────────────────
WORKER_NAMES=""
for i in $(seq 1 "$NUM_WORKERS"); do
    WORKER_NAMES="$WORKER_NAMES nexus-ner-$i"
done

echo "Creating $NUM_WORKERS NER worker VMs..."
# shellcheck disable=SC2086
gcloud compute instances create $WORKER_NAMES \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --source-instance-template="$TEMPLATE_NAME"

echo ""
echo "=== Done ==="
echo "Workers created: $NUM_WORKERS"
echo "Monitor NER queue depth:"
echo "  docker exec nexus-rabbitmq rabbitmqctl list_queues name messages consumers"
echo ""
echo "To tear down:"
echo "  bash scripts/infra/delete_ner_workers.sh"
