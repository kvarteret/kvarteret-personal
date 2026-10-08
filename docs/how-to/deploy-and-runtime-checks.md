# Deploy and Runtime Checks

This page covers runtime checks around the current Vercel deployment shape.

## Build Inputs

Vercel uses:

    api/index.py
    vercel.json
    scripts/prepare_vercel_static.py

The build prepares static assets so `/static/...` is served directly from `public/static`, while non-static routes go to the FastAPI ASGI app.

## Local Preflight

Run:

    kv test
    kv openapi --check
    bun run build:css
    python scripts/prepare_vercel_static.py

Then start locally:

    kv run

Check:

    curl http://127.0.0.1:8000/health

## Production Runtime Checks

Check health:

    curl https://personal.samfunnetibergen.no/health

Check now-playing shape:

    curl https://personal.samfunnetibergen.no/api/now-playing

Do not paste secrets into terminal history. For authenticated checks, use short-lived test credentials and redact bearer tokens from shared logs.

## Deployment Configuration Notes

On Vercel the app opens one database connection per request (`NullPool`). Do not keep pooled connections on serverless instances: many warm instances each holding a connection exhausted the Supabase session pooler's client slots and took production down on 2026-10-08.

Set `APP_ENV=production` explicitly. The app refuses to start when `APP_ENV` is
missing or is not one of `development`, `test`, or `production`.

Set `APP_SECRET_KEY` to a random value of at least 32 characters. The app refuses
production startup when the secret is still `change-me` or is too short.

Set `APP_PUBLIC_BASE_URL=https://personal.samfunnetibergen.no` for production email links
and OAuth callbacks. Production startup requires an HTTPS origin without embedded
credentials, a path, query, or fragment.

Keep `.vercelignore` excluding local-only archives such as `data/`.
