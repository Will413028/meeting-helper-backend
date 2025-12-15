.PHONY: run
run:
	uv run fastapi dev ./src/main.py --host 0.0.0.0 --port 8701

.PHONY: run-https
run-https:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem

.PHONY: generate-cert
generate-cert:
	@mkdir -p certs
	@openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes -subj "/C=TW/ST=Taiwan/L=Taipei/O=Development/CN=localhost"
	@echo "Self-signed certificate generated in ./certs/"

.PHONY: lint
lint:
	uv run ruff format
	uv run ruff check --fix

.PHONY: install
install:
	uv sync

.PHONY: migration
migration:
	uv run alembic upgrade head

.PHONY: generate_migration
generate_migration:
	@read -p "Enter migration name: " migration_name; \
	uv run alembic revision --autogenerate -m "$${migration_name}"

.PHONY: kill-port 
kill-port:
	@if [ -z "$(PORT)" ]; then \
		echo "❌ 請用 make kill-port PORT=8701 指定埠號"; \
		exit 1; \
	fi; \
	echo "🔍 檢查 port $(PORT) 是否被佔用..."; \
	if lsof -i :$(PORT) >/dev/null 2>&1; then \
		echo "⚠️  Port $(PORT) 已被佔用，正在關閉程序..."; \
		lsof -ti :$(PORT) | xargs kill -9 || true; \
		echo "✅ Port $(PORT) 已釋放。"; \
	else \
		echo "✅ Port $(PORT) 沒有被佔用。"; \
	fi
