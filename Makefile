.PHONY: help install css assets css-watch run test lint lint-imports audit openapi openapi-check migrate schema-drift smoke-auth

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
