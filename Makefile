-include .env

.PHONY: help install css css-watch run test smoke-auth upload-legacy-images

help:
	@printf "Targets:\n"
	@printf "  make install    Install Python and frontend dependencies\n"
	@printf "  make css        Build Tailwind CSS once\n"
	@printf "  make css-watch  Watch and rebuild Tailwind CSS\n"
	@printf "  make run        Build CSS and start the FastAPI app\n"
	@printf "  make test       Run the test suite\n"
	@printf "  make smoke-auth Run a live auth create-login-cleanup smoke test\n"
	@printf "  make upload-legacy-images Upload recovered Azure images into Supabase Storage\n"

install:
	uv sync
	npm install

css:
	npm run build:css

css-watch:
	npm run watch:css

run: css
	uv run uvicorn app.main:create_app --factory --reload

test:
	uv run pytest

smoke-auth:
	uv run python scripts/live_auth_smoke.py

upload-legacy-images:
	uv run python scripts/upload_legacy_images_to_supabase.py
