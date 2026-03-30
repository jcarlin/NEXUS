#!/bin/bash
# Tear down the ingest worker MIG, autoscaler, and instance template.
#
# Does NOT delete the firewall rule (shared with NER workers).
# Does NOT touch the main VM or any data.
#
# Usage:
#   bash scripts/infra/teardown_worker_mig.sh

set -euo pipefail

PROJECT="vault-ai-487703"
ZONE="us-west1-a"
MIG_NAME="nexus-ingest-mig"
TEMPLATE_NAME="nexus-ingest-worker"

echo "=== Tearing down Ingest Worker MIG ==="

# ── Stop autoscaler ─────────────────────────────────────────────
echo "Removing autoscaler..."
gcloud compute instance-groups managed stop-autoscaling "$MIG_NAME" \
    --zone="$ZONE" --project="$PROJECT" 2>/dev/null || true

# ── Delete MIG (scales down all VMs first) ──────────────────────
echo "Deleting MIG $MIG_NAME (this will terminate all satellite VMs)..."
gcloud compute instance-groups managed delete "$MIG_NAME" \
    --zone="$ZONE" --project="$PROJECT" --quiet 2>/dev/null || true

# ── Delete instance template ────────────────────────────────────
echo "Deleting instance template $TEMPLATE_NAME..."
gcloud compute instance-templates delete "$TEMPLATE_NAME" \
    --project="$PROJECT" --quiet 2>/dev/null || true

echo ""
echo "=== Teardown Complete ==="
echo "MIG and template removed. No further billing for satellite workers."
echo "Firewall rule preserved (shared with NER workers)."
echo "Main VM and all data untouched."
