.PHONY: help install css assets css-watch run test lint lint-imports audit openapi openapi-check migrate schema-drift smoke-auth dev-up dev-down dev-reset dev-run dev-snapshot

help:
	@printf "Targets:\n"
	@printf "  make install    Install Python and frontend dependencies\n"
	@printf "  make css        Build Tailwind CSS once\n"
	@printf "  make assets     Build CSS and browser assets once\n"
	@printf "  make css-watch  Watch and rebuild Tailwind CSS\n"
	@printf "  make run        Build CSS and start the FastAPI app\n"
	@printf "  make test       Run the test suite\n"
	@printf "  make lint       Run Ruff lint checks\n"
	@printf "  make lint-imports Check import-linter contracts\n"
	@printf "  make audit      Run dependency vulnerability audit\n"
	@printf "  make openapi    Regenerate the checked-in OpenAPI artifact\n"
	@printf "  make openapi-check Verify the checked-in OpenAPI artifact is current\n"
	@printf "  make migrate    Apply Alembic migrations to the configured database\n"
	@printf "  make schema-drift Compare DB schema to SQLAlchemy metadata\n"
	@printf "  make smoke-auth Run a live auth create-login-cleanup smoke test\n"
	@printf "  make dev-up     Start + migrate + seed the local dev database (Docker)\n"
	@printf "  make dev-run    Run the app against the local dev database\n"
	@printf "  make dev-reset  Recreate the local dev database from scratch\n"
	@printf "  make dev-down   Stop the local dev database\n"
	@printf "  make dev-snapshot Build an anonymized seed from production (maintainers)\n"

install:
	uv sync
	bun install

css:
	bun run build:css

assets:
	bun run build:assets

css-watch:
	bun run watch:css

run: assets
	uv run uvicorn app.main:create_app --factory --reload

test:
	uv run pytest

lint:
	uv run ruff check .

lint-imports:
	uv run lint-imports

audit:
	uv run pip-audit

openapi:
	uv run python scripts/export_openapi.py

openapi-check:
	uv run python scripts/export_openapi.py --check

migrate:
	uv run alembic upgrade head

schema-drift:
	uv run python scripts/check_schema_drift.py

smoke-auth:
	uv run python scripts/live_auth_smoke.py

# ── Local development harness ───────────────────────────────────────
# Dockerized Postgres on :55432, migrated and seeded. No production
# access required; see docs/how-to/local-development.md.

DEV_DB_URL ?= postgresql+asyncpg://postgres:postgres@localhost:55432/kvarteret_personal_dev
DEV_ADMIN_EMAIL ?= dev@kvarteret.dev
DEV_ADMIN_PASSWORD ?= dev-password

dev-up:
	docker compose -f docker-compose.dev.yml up -d --wait
	DEV_DATABASE_URL=$(DEV_DB_URL) DEV_ADMIN_EMAIL=$(DEV_ADMIN_EMAIL) uv run python scripts/dev/bootstrap.py

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-reset:
	docker compose -f docker-compose.dev.yml down -v
	$(MAKE) dev-up

dev-run: assets
	DATABASE_URL=$(DEV_DB_URL) APP_ENV=development \
	DEV_ADMIN_EMAIL=$(DEV_ADMIN_EMAIL) DEV_ADMIN_PASSWORD=$(DEV_ADMIN_PASSWORD) \
	SUPABASE_URL= SUPABASE_SECRET_KEY= SMTP_SERVER= \
	AZURE_BLOB_CONNECTION_STRING= AZURE_BLOB_ACCOUNT_NAME= AZURE_BLOB_ACCOUNT_KEY= \
	uv run uvicorn app.main:create_app --factory --reload

dev-snapshot:
	DEV_DATABASE_URL=$(DEV_DB_URL) uv run python scripts/dev/make_anonymized_snapshot.py
