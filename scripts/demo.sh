#!/bin/bash
set -euo pipefail

echo "=== NEXUS Demo Setup ==="
echo ""

# Resolve project root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV="$PROJECT_ROOT/.venv/bin"

# Check venv exists
if [ ! -f "$VENV/python" ]; then
    echo "ERROR: Python virtual environment not found at .venv/"
    echo "Run 'make install' first."
    exit 1
fi

# 1. Infrastructure
echo "--- Starting infrastructure ---"
docker compose up -d
echo "Waiting for services..."

# Wait for PostgreSQL
until docker compose exec -T postgres pg_isready -U nexus > /dev/null 2>&1; do
    sleep 1
done
echo "  PostgreSQL: ready"

# Wait for Redis
until docker compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    sleep 1
done
echo "  Redis: ready"

# Wait for Qdrant
until curl -sf http://localhost:6333/healthz > /dev/null 2>&1; do
    sleep 1
done
echo "  Qdrant: ready"

# Wait for MinIO
until curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; do
    sleep 1
done
echo "  MinIO: ready"

echo ""

# 2. Migrations
echo "--- Running database migrations ---"
"$VENV/alembic" upgrade head
echo ""

# 3. Admin user
echo "--- Ensuring admin user ---"
"$VENV/python" scripts/fix_admin_password.py
echo ""

# 4. Generate docs
echo "--- Generating test documents ---"
"$VENV/python" -m scripts.generate_test_docs
echo ""

# 5. Start API + Worker in background
echo "--- Starting API server and Celery worker ---"
"$VENV/uvicorn" app.main:app --port 8000 &
API_PID=$!

"$VENV/celery" -A workers.celery_app worker -l info -c 1 &
WORKER_PID=$!

# Cleanup function
cleanup() {
    echo ""
    echo "--- Stopping background services ---"
    kill $API_PID $WORKER_PID 2>/dev/null || true
    wait $API_PID $WORKER_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for API health
echo "Waiting for API..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo "  API: ready"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: API failed to start within 60 seconds"
        exit 1
    fi
    sleep 1
done
echo ""

# 6. Seed demo data
echo "--- Seeding demo data ---"
"$VENV/python" scripts/seed_demo.py
echo ""

echo "============================================"
echo "  NEXUS Demo setup complete!"
echo ""
echo "  Run 'make dev' to start the platform."
echo ""
echo "  Login credentials:"
echo "    admin@example.com    / password123  (admin)"
echo "    attorney@nexus.dev   / password123  (attorney)"
echo "    paralegal@nexus.dev  / password123  (paralegal)"
echo "    reviewer@nexus.dev   / password123  (reviewer)"
echo ""
echo "  URLs:"
echo "    Frontend: http://localhost:5173"
echo "    API:      http://localhost:8000/api/v1"
echo "    API Docs: http://localhost:8000/docs"
echo "============================================"
