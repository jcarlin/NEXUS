.PHONY: help install up down dev stop api worker frontend test migrate logs demo seed-demo

VENV := .venv/bin
SERVICES ?=

help: ## Show all targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python + frontend dependencies
	uv venv --allow-existing
	uv pip install -e ".[dev]"
	cd frontend && npm install

up: ## Start infrastructure services (Docker)
	docker compose up -d
	@echo ""
	@docker compose ps

down: ## Stop infrastructure services
	docker compose down

dev: up migrate ## Start everything (infra + API + worker + frontend)
	$(VENV)/honcho start -f Procfile.dev

stop: ## Stop all dev processes (API, worker, frontend, flower)
	@echo "Stopping dev processes..."
	-@pkill -f 'uvicorn app.main:app' 2>/dev/null
	-@pkill -f 'celery -A workers.celery_app worker' 2>/dev/null
	-@pkill -f 'celery -A workers.celery_app flower' 2>/dev/null
	-@pkill -f 'node.*frontend.*vite' 2>/dev/null
	-@pkill -f 'honcho start -f Procfile.dev' 2>/dev/null
	@echo "Done."

api: ## Start API server with auto-reload
	$(VENV)/uvicorn app.main:app --reload --port 8000

worker: ## Start Celery worker (autoscale: max 4, min 1)
	$(VENV)/celery -A workers.celery_app worker -l info --autoscale=4,1

frontend: ## Start React frontend dev server
	cd frontend && npm run dev

test: ## Run full test suite (parallel)
	$(VENV)/pytest tests/ -v -n auto

test-fast: ## Run tests for a specific module (usage: make test-fast MOD=query)
	$(VENV)/pytest tests/test_$(MOD)/ -v

migrate: ## Run database migrations
	$(VENV)/alembic upgrade head

logs: ## Tail Docker service logs (use SERVICES=redis,postgres to filter)
	docker compose logs -f $(SERVICES)

demo: install up migrate  ## One-time demo setup: seed all data
	bash scripts/demo.sh

seed-demo:  ## Re-seed demo data (requires running API + worker)
	$(VENV)/python -m scripts.generate_test_docs
	$(VENV)/python scripts/seed_demo.py
