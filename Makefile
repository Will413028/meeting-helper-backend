.PHONY: run
run:
	uv run fastapi dev ./src/main.py

.PHONY: run-prod
run-prod:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

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

.PHONY: deploy-gitlab
deploy-gitlab:
	ansible-playbook -i ./ansible/gitlab_inventory.ini ./ansible/gitlab_playbook.yml
