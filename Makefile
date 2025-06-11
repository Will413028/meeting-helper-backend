.PHONY: run
run:
	uv run fastapi dev ./src/main.py --host 0.0.0.0 --port 8701

.PHONY: run-prod
run-prod:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8701

.PHONY: lint
lint:
	uv run ruff format
	uv run ruff check --fix

.PHONY: test
test:
	uv run python test_api.py

.PHONY: install
install:
	uv sync

.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf uploads/*

.PHONY: setup-env
setup-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file. Please update it with your Hugging Face token."; \
	else \
		echo ".env file already exists."; \
	fi

.PHONY: migration
migration:
	uv run alembic upgrade head

.PHONY: generate_migration
generate_migration:
	@read -p "Enter migration name: " migration_name; \
	uv run alembic revision --autogenerate -m "$${migration_name}"
