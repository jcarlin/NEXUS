#!/usr/bin/env bash
# =============================================================================
# cloud-deploy.sh — Deploy NEXUS to a GCP Compute Engine VM
# =============================================================================
# Usage: ./scripts/cloud-deploy.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - .env file in project root with ANTHROPIC_API_KEY and OPENAI_API_KEY
#
# This script:
#   1. Creates a GCP project (or reuses existing)
#   2. Creates a VM with Docker pre-installed
#   3. Copies config, clones the repo, builds and starts all services
#   4. Runs migrations + seeds admin user
#   5. Verifies the health endpoint
# =============================================================================

set -euo pipefail

# --- Config ---
PROJECT_ID="${GCP_PROJECT_ID:-vault-ai-487703}"
BILLING_ACCOUNT="${GCP_BILLING_ACCOUNT:-013011-FB785A-E3866B}"
ZONE="us-central1-a"
REGION="us-central1"
VM_NAME="nexus-demo"
MACHINE_TYPE="e2-standard-2"
DISK_SIZE="50GB"
REPO_URL="https://github.com/jcarlin/NEXUS.git"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# --- Preflight ---
if [[ ! -f "$ENV_FILE" ]]; then
    err ".env file not found at $ENV_FILE"
    exit 1
fi

if ! command -v gcloud &>/dev/null; then
    err "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Extract API keys from local .env
ANTHROPIC_KEY=$(grep '^ANTHROPIC_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
OPENAI_KEY=$(grep '^OPENAI_API_KEY=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$ANTHROPIC_KEY" || -z "$OPENAI_KEY" ]]; then
    err "ANTHROPIC_API_KEY and OPENAI_API_KEY must be set in $ENV_FILE"
    exit 1
fi

# Generate passwords
JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n/+=' | head -c 64)
PG_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=' | head -c 24)
NEO4J_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=' | head -c 24)
MINIO_SECRET=$(openssl rand -base64 24 | tr -d '\n/+=' | head -c 24)
ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -d '\n/+=' | head -c 16)

# =============================================================================
# Step 1: GCP Project
# =============================================================================
log "Setting up GCP project: $PROJECT_ID"

if gcloud projects describe "$PROJECT_ID" &>/dev/null; then
    log "Project $PROJECT_ID already exists — reusing"
else
    log "Creating project $PROJECT_ID..."
    gcloud projects create "$PROJECT_ID" --name="NEXUS Demo" --quiet
    # Link billing (only needed for new projects)
    log "Linking billing account..."
    gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" --quiet
fi

gcloud config set project "$PROJECT_ID" --quiet

# Enable Compute Engine
log "Enabling Compute Engine API..."
gcloud services enable compute.googleapis.com --quiet

# Wait for API to be ready
sleep 5

# =============================================================================
# Step 2: Firewall rules
# =============================================================================
log "Configuring firewall rules..."

if ! gcloud compute firewall-rules describe nexus-allow-http --project="$PROJECT_ID" &>/dev/null; then
    gcloud compute firewall-rules create nexus-allow-http \
        --action=ALLOW \
        --rules=tcp:8000 \
        --source-ranges=0.0.0.0/0 \
        --target-tags=nexus-web \
        --description="NEXUS API (test deploy)" \
        --quiet
fi

if ! gcloud compute firewall-rules describe nexus-allow-ssh --project="$PROJECT_ID" &>/dev/null; then
    gcloud compute firewall-rules create nexus-allow-ssh \
        --action=ALLOW \
        --rules=tcp:22 \
        --source-ranges=0.0.0.0/0 \
        --target-tags=nexus-web \
        --description="SSH access" \
        --quiet
fi

# =============================================================================
# Step 3: Create VM
# =============================================================================
log "Creating VM: $VM_NAME ($MACHINE_TYPE, $DISK_SIZE SSD)..."

if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" &>/dev/null; then
    warn "VM $VM_NAME already exists. Starting if stopped..."
    gcloud compute instances start "$VM_NAME" --zone="$ZONE" --quiet 2>/dev/null || true
else
    gcloud compute instances create "$VM_NAME" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --image-family=ubuntu-2404-lts-amd64 \
        --image-project=ubuntu-os-cloud \
        --boot-disk-size="$DISK_SIZE" \
        --boot-disk-type=pd-balanced \
        --tags=nexus-web \
        --quiet
fi

# Wait for VM to be ready
log "Waiting for VM to be ready..."
sleep 15

# Get external IP
EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
log "VM external IP: $EXTERNAL_IP"

# =============================================================================
# Step 4: Build .env for cloud
# =============================================================================
log "Generating cloud .env file..."

CLOUD_ENV=$(mktemp)
cat > "$CLOUD_ENV" <<ENVEOF
# Auto-generated for NEXUS cloud deploy
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
OPENAI_API_KEY=$OPENAI_KEY
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5-20250929
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=100
POSTGRES_PASSWORD=$PG_PASSWORD
NEO4J_PASSWORD=$NEO4J_PASSWORD
MINIO_ACCESS_KEY=nexus-admin
MINIO_SECRET_KEY=$MINIO_SECRET
MINIO_BUCKET=documents
MINIO_USE_SSL=false
JWT_SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
CORS_ALLOWED_ORIGINS=*
REQUIRE_MATTER_HEADER=true
CELERY_CONCURRENCY=2
CHUNK_SIZE=512
CHUNK_OVERLAP=64
ENABLE_AGENTIC_PIPELINE=true
ENABLE_CITATION_VERIFICATION=true
ENABLE_EMAIL_THREADING=true
ENABLE_VISUAL_EMBEDDINGS=false
ENABLE_RELATIONSHIP_EXTRACTION=false
ENABLE_RERANKER=false
ENABLE_SPARSE_EMBEDDINGS=false
ENABLE_AI_AUDIT_LOGGING=true
ENVEOF

# =============================================================================
# Step 5: Deploy to VM
# =============================================================================
log "Deploying to VM..."

# Copy .env file to VM
gcloud compute scp "$CLOUD_ENV" "$VM_NAME:~/nexus-cloud.env" --zone="$ZONE" --quiet
rm -f "$CLOUD_ENV"

# Run setup script on VM
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --quiet --command="bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

echo "[remote] Installing Docker..."
if ! command -v docker &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker.io docker-compose-v2 git > /dev/null 2>&1
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
fi

echo "[remote] Cloning repository..."
if [[ -d ~/nexus ]]; then
    cd ~/nexus && git pull --quiet
else
    git clone --quiet https://github.com/jcarlin/NEXUS.git ~/nexus
fi

cd ~/nexus

echo "[remote] Setting up environment..."
cp ~/nexus-cloud.env .env

echo "[remote] Building Docker images (this takes a few minutes)..."
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml build --quiet 2>/dev/null || \
    sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml build

echo "[remote] Starting services..."
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "[remote] Waiting for services to be healthy..."
sleep 30

echo "[remote] Running database migrations..."
sudo docker compose exec -T api alembic upgrade head

echo "[remote] Seeding admin user..."
sudo docker compose exec -T -e ADMIN_EMAIL=admin@nexus.local -e ADMIN_PASSWORD=PLACEHOLDER api python scripts/seed_admin.py

echo "[remote] Checking service health..."
for i in {1..10}; do
    if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo "[remote] Health check passed!"
        curl -s http://localhost:8000/api/v1/health
        echo ""
        break
    fi
    echo "[remote] Waiting for API... (attempt $i/10)"
    sleep 10
done

echo "[remote] Container status:"
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
REMOTE_SCRIPT

# Replace the placeholder admin password
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --quiet --command="
cd ~/nexus && sudo docker compose exec -T -e ADMIN_EMAIL=admin@nexus.local -e ADMIN_PASSWORD='$ADMIN_PASSWORD' api python scripts/seed_admin.py 2>/dev/null || true
"

# =============================================================================
# Step 6: Verify
# =============================================================================
log ""
log "============================================"
log "  NEXUS Cloud Deploy Complete!"
log "============================================"
log ""
log "  API URL:    http://$EXTERNAL_IP:8000"
log "  Health:     http://$EXTERNAL_IP:8000/api/v1/health"
log "  API Docs:   http://$EXTERNAL_IP:8000/docs"
log ""
log "  Admin login:"
log "    Email:    admin@nexus.local"
log "    Password: $ADMIN_PASSWORD"
log ""
log "  GCP Project: $PROJECT_ID"
log "  VM:          $VM_NAME ($ZONE)"
log ""
log "  To stop (avoid charges):"
log "    ./scripts/cloud-teardown.sh"
log ""
log "  To SSH into the VM:"
log "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
log ""

# Save deploy info for teardown script
cat > "$PROJECT_ROOT/.cloud-deploy-info" <<EOF
PROJECT_ID=$PROJECT_ID
VM_NAME=$VM_NAME
ZONE=$ZONE
EXTERNAL_IP=$EXTERNAL_IP
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF

log "Deploy info saved to .cloud-deploy-info"
