.PHONY: help install lint test benchmark benchmark-v2 benchmark-gemini public-corpus run demo docker-build docker-up docker-down docker-logs docker-ps clean

help: ## List available targets.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the project and development dependencies.
	python -m pip install -e '.[dev]'

lint: ## Run static checks.
	python -m ruff check .

test: ## Run the test suite.
	python -m pytest

benchmark: ## Recompute the versioned synthetic quality benchmark.
	python scripts/run_benchmark.py --output artifacts/evaluation-report.json

benchmark-v2: ## Evaluate the held-out split of the larger synthetic challenge set.
	python scripts/run_benchmark_v2.py --split test --judge deterministic

benchmark-gemini: ## Add advisory Gemini judging (requires GEMINI_API_KEY).
	python scripts/run_benchmark_v2.py --split test --judge both

public-corpus: ## Acquire the allowlisted official EU corpus with provenance.
	python scripts/fetch_public_corpus.py

run: ## Run the API locally with automatic reload.
	python -m uvicorn app.main:app --reload --host 0.0.0.0 --port $${API_PORT:-8000}

demo: docker-up ## Start the stack and print the interactive demo URL.
	@echo "Demo: http://localhost:$${API_PORT:-8000}/demo"

docker-build: ## Build the API image.
	docker compose build

docker-up: ## Start the complete local stack and wait for healthchecks.
	docker compose up --build --detach --wait

docker-down: ## Stop the stack without deleting persisted data.
	docker compose down

docker-logs: ## Follow logs from all services.
	docker compose logs --follow

docker-ps: ## Display container and health status.
	docker compose ps

clean: ## Remove local Python caches and build artifacts.
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist
