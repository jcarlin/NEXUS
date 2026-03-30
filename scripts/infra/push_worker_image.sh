#!/bin/bash
# Tag and push the nexus-api Docker image to GCR for satellite workers.
#
# Run on the main VM (nexus-ingest) where the image is already built.
# This is read-only on the running container — safe during active ingestion.
#
# Usage:
#   bash scripts/infra/push_worker_image.sh [TAG]
#   bash scripts/infra/push_worker_image.sh v1.19.0

set -euo pipefail

TAG="${1:-latest}"
PROJECT="vault-ai-487703"
LOCAL_IMAGE="nexus-api"
GCR_IMAGE="gcr.io/${PROJECT}/nexus-api"

echo "=== Push Worker Image to GCR ==="
echo "Local: $LOCAL_IMAGE"
echo "Remote: $GCR_IMAGE:$TAG"
echo ""

# Authenticate to GCR
gcloud auth configure-docker gcr.io --quiet

# Tag
sudo docker tag "$LOCAL_IMAGE" "$GCR_IMAGE:$TAG"

# Also tag as latest if a specific tag was given
if [ "$TAG" != "latest" ]; then
    sudo docker tag "$LOCAL_IMAGE" "$GCR_IMAGE:latest"
fi

# Push
sudo docker push "$GCR_IMAGE:$TAG"
if [ "$TAG" != "latest" ]; then
    sudo docker push "$GCR_IMAGE:latest"
fi

echo ""
echo "=== Done ==="
echo "Image pushed: $GCR_IMAGE:$TAG"
echo "Satellites will pull this on next boot."
