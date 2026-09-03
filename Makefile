# aether-eoc-reference — developer entrypoints.
#
# Every target works with NO API keys. The agents fall back to deterministic
# fixture mode when LLM_PROVIDER=none (see docs/AI_SPEC.md).
#
# Windows users without GNU make: each target is a one-liner you can paste,
# and the same commands exist as npm scripts. See README "Quick start".

API_DIR := apps/api
WEB_DIR := apps/web

# Override to dodge port collisions:  make dev API_PORT=8090 WEB_PORT=3100
API_PORT ?= 8080
WEB_PORT ?= 3000

.DEFAULT_GOAL := help
.PHONY: help install seed dev dev-api dev-web test test-api test-web lint typecheck fmt up down clean reset

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install API (uv) and web (npm) dependencies
	cd $(API_DIR) && uv sync
	cd $(WEB_DIR) && npm install

seed: ## Create the SQLite database and load the synthetic heat-surge scenario
	cd $(API_DIR) && uv run python -m app.seed

reset: ## Delete the local database, then re-seed from fixtures
	rm -f data/eoc.db
	$(MAKE) seed

dev-api: ## Run the FastAPI server (REST + WebSocket) with reload
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --port $(API_PORT)

dev-web: ## Run the Next.js dev server
	cd $(WEB_DIR) && npm run dev -- --port $(WEB_PORT)

dev: ## Run API and web together (Ctrl-C stops both)
	@echo "API  -> http://localhost:$(API_PORT)/api/docs"
	@echo "WEB  -> http://localhost:$(WEB_PORT)"
	@$(MAKE) -j2 dev-api dev-web

test: test-api test-web ## Run the full test suite (no API key required)

test-api: ## Run pytest against the API
	cd $(API_DIR) && uv run python -m pytest -q

test-web: ## Run vitest against the web app
	cd $(WEB_DIR) && npm run test -- --run

lint: ## Ruff + ESLint
	cd $(API_DIR) && uv run ruff check .
	cd $(WEB_DIR) && npm run lint

typecheck: ## Pyright + tsc
	cd $(API_DIR) && uv run pyright
	cd $(WEB_DIR) && npm run typecheck

fmt: ## Format Python and TypeScript
	cd $(API_DIR) && uv run ruff format .
	cd $(WEB_DIR) && npm run format

up: ## Start the whole stack in Docker
	docker compose up --build

down: ## Stop the Docker stack
	docker compose down -v

clean: ## Remove build artifacts and the local database
	rm -rf $(WEB_DIR)/.next $(WEB_DIR)/node_modules $(API_DIR)/.venv data/eoc.db
