# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Ambient Scribe Makefile
.PHONY: help dev up down build push logs fmt lint test clean install bootstrap seed

# Configuration
DEV_COMPOSE := infra/compose.dev.yml
PROD_COMPOSE := infra/compose.prod.yml
DOCKER_REGISTRY ?= ambient-scribe
VERSION ?= latest

## Help
help: ## Show this help message
	@echo "Ambient Scribe - Medical Transcription & Note Generation"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Development
dev: validate-env ## Start development environment
	docker compose -f $(DEV_COMPOSE) up --build -d

dev-nim: validate-env ## Start development environment with local NIM
	docker compose -f $(DEV_COMPOSE) --profile riva-nim up --build -d

validate-env: ## Validate environment configuration
	@./scripts/validate-env.sh

dev-logs: ## Follow development logs
	docker compose -f $(DEV_COMPOSE) logs -f

dev-logs-nim: ## Follow development logs (with NIM profile)
	docker compose -f $(DEV_COMPOSE) --profile riva-nim logs -f

dev-down: ## Stop development environment
	docker compose -f $(DEV_COMPOSE) down

dev-down-nim: ## Stop development environment (with NIM profile)
	docker compose -f $(DEV_COMPOSE) --profile riva-nim down

##@ Production
up: ## Start production environment
	docker compose -f $(PROD_COMPOSE) up -d

up-nim: ## Start production environment with local NIM
	docker compose -f $(PROD_COMPOSE) --profile riva-nim up -d

down: ## Stop production environment
	docker compose -f $(PROD_COMPOSE) down

down-nim: ## Stop production environment (with NIM profile)
	docker compose -f $(PROD_COMPOSE) --profile riva-nim down

restart: ## Restart production environment
	docker compose -f $(PROD_COMPOSE) restart

restart-nim: ## Restart production environment (with NIM profile)
	docker compose -f $(PROD_COMPOSE) --profile riva-nim restart

##@ Building & Deployment
build: ## Build Docker images
	docker build -f infra/docker/api.Dockerfile -t $(DOCKER_REGISTRY)/api:$(VERSION) .
	docker build -f infra/docker/ui.Dockerfile -t $(DOCKER_REGISTRY)/ui:$(VERSION) .

push: build ## Build and push Docker images
	docker push $(DOCKER_REGISTRY)/api:$(VERSION)
	docker push $(DOCKER_REGISTRY)/ui:$(VERSION)

##@ Monitoring & Logs
logs: ## View production logs
	docker compose -f $(PROD_COMPOSE) logs -f

logs-api: ## View API logs only
	docker compose -f $(PROD_COMPOSE) logs -f api

logs-ui: ## View UI logs only
	docker compose -f $(PROD_COMPOSE) logs -f ui

health: ## Check service health
	@echo "Checking service health..."
	@curl -f http://localhost:8000/api/health/ || echo "API not responding"
	@curl -f http://localhost:5173/ || echo "UI not responding"


fmt: ## Format code
	cd apps/api && black . && isort .
	cd apps/ui && npm run format

lint: ## Run linters
	cd apps/api && ruff check . && mypy .
	cd apps/ui && npm run lint

test: ## Run tests
	cd apps/api && pytest
	cd apps/ui && npm run test

##@ Database & Setup
bootstrap: ## Initialize the application
	./scripts/bootstrap.sh

clean: ## Clean up containers and volumes
	docker compose -f $(DEV_COMPOSE) down -v
	docker compose -f $(PROD_COMPOSE) down -v
	docker system prune -f

reset: clean bootstrap ## Reset and reinitialize everything

##@ Backup & Restore
backup: ## Backup application data
	@echo "Creating backup..."
	docker compose -f $(PROD_COMPOSE) exec -T api tar -czf - /app/uploads > backup_$(shell date +%Y%m%d_%H%M%S).tar.gz
	@echo "Backup created: backup_$(shell date +%Y%m%d_%H%M%S).tar.gz"

restore: ## Restore from backup (Usage: make restore BACKUP_FILE=backup.tar.gz)
	@echo "Restoring from $(BACKUP_FILE)..."
	docker compose -f $(PROD_COMPOSE) exec -T api tar -xzf - -C / < $(BACKUP_FILE)

##@ Local Development (without Docker)
dev-api: ## Run API server locally
	cd apps/api && uvicorn ambient_scribe.main:app --reload --host 0.0.0.0 --port 8000

dev-ui: ## Run UI development server locally (verbose)
	@echo "Setting up UI development environment..."
	cd apps/ui && \
		echo "Cleaning up existing installation..." && \
		rm -rf node_modules package-lock.json && \
		echo "Running npm install (verbose)..." && \
		npm install --force --loglevel verbose --registry https://registry.npmjs.org/ && \
		echo "Installing local NVIDIA packages (verbose)..." && \
		npm install ./kui-foundations-0.403.0.tgz ./kui-react-0.402.1.tgz ./nv-brand-assets-icons-3.8.0.tgz ./nv-brand-assets-react-icons-inline-3.8.0.tgz --no-save --prefer-offline --no-audit --no-fund --loglevel verbose --registry https://registry.npmjs.org/ || true && \
		echo "Starting development server..." && \
		npm run dev --loglevel verbose

##@ Configuration
env: ## Copy environment template
	cp apps/api/dot_env_example apps/api/.env
	@echo "Environment file created. Please edit apps/api/.env with your configuration."

##@ Utilities
shell-api: ## Open shell in API container
	docker compose -f $(DEV_COMPOSE) exec api /bin/bash

shell-ui: ## Open shell in UI container
	docker compose -f $(DEV_COMPOSE) exec ui /bin/sh

ps: ## Show running containers
	docker compose -f $(DEV_COMPOSE) ps

top: ## Show container resource usage
	docker stats

# Default target
.DEFAULT_GOAL := help
