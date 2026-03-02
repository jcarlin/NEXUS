.PHONY: help install up down dev api worker frontend test migrate logs demo seed-demo

VENV := .venv/bin
SERVICES ?=

help: ## Show all targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python + frontend dependencies
	uv venv
	$(VENV)/pip install -e ".[dev]"
	cd frontend && npm install

up: ## Start infrastructure services (Docker)
	docker compose up -d
	@echo ""
	@docker compose ps

down: ## Stop infrastructure services
	docker compose down

dev: up migrate ## Start everything (infra + API + worker + frontend)
	$(VENV)/honcho start -f Procfile.dev

api: ## Start API server with auto-reload
	$(VENV)/uvicorn app.main:app --reload --port 8000

worker: ## Start Celery worker with auto-reload on .py changes
	$(VENV)/watchmedo auto-restart --directory=./app --directory=./workers --pattern='*.py' --recursive -- $(VENV)/celery -A workers.celery_app worker -l info -c 1

frontend: ## Start React frontend dev server
	cd frontend && npm run dev

test: ## Run test suite
	$(VENV)/pytest tests/ -v

migrate: ## Run database migrations
	$(VENV)/alembic upgrade head

logs: ## Tail Docker service logs (use SERVICES=redis,postgres to filter)
	docker compose logs -f $(SERVICES)

demo: install up migrate  ## One-time demo setup: seed all data
	bash scripts/demo.sh

seed-demo:  ## Re-seed demo data (requires running API + worker)
	$(VENV)/python -m scripts.generate_test_docs
	$(VENV)/python scripts/seed_demo.py
