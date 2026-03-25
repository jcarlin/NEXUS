#!/bin/bash
# Tear down NER worker VMs, instance template, and firewall rule.
#
# Usage:
#   bash scripts/infra/delete_ner_workers.sh [NUM_WORKERS]
#   bash scripts/infra/delete_ner_workers.sh 6

set -euo pipefail

NUM_WORKERS="${1:-6}"
PROJECT="vault-ai-487703"
ZONE="us-west1-a"

echo "=== Tearing down NER workers ==="

# ── Delete worker VMs ───────────────────────────────────────────
WORKER_NAMES=""
for i in $(seq 1 "$NUM_WORKERS"); do
    WORKER_NAMES="$WORKER_NAMES nexus-ner-$i"
done

echo "Deleting $NUM_WORKERS worker VMs..."
# shellcheck disable=SC2086
gcloud compute instances delete $WORKER_NAMES \
    --zone="$ZONE" --project="$PROJECT" --quiet 2>/dev/null || true

# ── Delete instance template ────────────────────────────────────
echo "Deleting instance template..."
gcloud compute instance-templates delete nexus-ner-worker \
    --project="$PROJECT" --quiet 2>/dev/null || true

# ── Delete firewall rule ────────────────────────────────────────
echo "Deleting firewall rule..."
gcloud compute firewall-rules delete nexus-internal-services \
    --project="$PROJECT" --quiet 2>/dev/null || true

echo ""
echo "=== Teardown complete ==="
echo "NER workers, template, and firewall rule removed."
echo "No further billing for these resources."
