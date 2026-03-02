#!/usr/bin/env bash
# =============================================================================
# cloud-teardown.sh — Stop or delete the NEXUS cloud deployment
# =============================================================================
# Usage:
#   ./scripts/cloud-teardown.sh          # Stop VM (can restart later, ~$0.17/day disk)
#   ./scripts/cloud-teardown.sh --delete  # Delete VM + project entirely ($0/day)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INFO_FILE="$PROJECT_ROOT/.cloud-deploy-info"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[teardown]${NC} $*"; }
warn() { echo -e "${YELLOW}[teardown]${NC} $*"; }
err()  { echo -e "${RED}[teardown]${NC} $*" >&2; }

DELETE_MODE=false
if [[ "${1:-}" == "--delete" ]]; then
    DELETE_MODE=true
fi

# Load deploy info
if [[ -f "$INFO_FILE" ]]; then
    source "$INFO_FILE"
else
    err "No deploy info found at $INFO_FILE"
    err "Set PROJECT_ID, VM_NAME, and ZONE manually or re-run cloud-deploy.sh"
    exit 1
fi

PROJECT_ID="${PROJECT_ID:-}"
VM_NAME="${VM_NAME:-nexus-demo}"
ZONE="${ZONE:-us-central1-a}"

if [[ -z "$PROJECT_ID" ]]; then
    err "PROJECT_ID not set in $INFO_FILE"
    exit 1
fi

gcloud config set project "$PROJECT_ID" --quiet

if $DELETE_MODE; then
    log "DELETING all resources in project $PROJECT_ID..."

    # Delete VM
    if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" &>/dev/null; then
        log "Deleting VM $VM_NAME..."
        gcloud compute instances delete "$VM_NAME" --zone="$ZONE" --quiet
    else
        warn "VM $VM_NAME not found"
    fi

    # Delete firewall rules
    for rule in nexus-allow-http nexus-allow-ssh; do
        if gcloud compute firewall-rules describe "$rule" &>/dev/null; then
            log "Deleting firewall rule: $rule"
            gcloud compute firewall-rules delete "$rule" --quiet
        fi
    done

    # Optionally delete the project entirely
    log ""
    log "VM and firewall rules deleted."
    log "To delete the entire GCP project (removes ALL resources):"
    log "  gcloud projects delete $PROJECT_ID"
    log ""

    rm -f "$INFO_FILE"
    log "Deploy info cleaned up."

else
    # Just stop the VM
    if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" &>/dev/null; then
        log "Stopping VM $VM_NAME..."
        gcloud compute instances stop "$VM_NAME" --zone="$ZONE" --quiet
        log "VM stopped. Disk charges only (~\$0.17/day)."
        log ""
        log "To restart later:"
        log "  gcloud compute instances start $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
        log ""
        log "To delete everything:"
        log "  ./scripts/cloud-teardown.sh --delete"
    else
        warn "VM $VM_NAME not found in zone $ZONE"
    fi
fi
