## Kvarteret Personal

This repository contains the in-progress FastAPI, HTMX, Tailwind, Supabase, and PostgREST replacement for the old Kvarteret personal system.

The living execution plan for the rewrite is in [plans/fastapi-rewrite.md](plans/fastapi-rewrite.md). Repository-local planning rules are in [PLANS.md](PLANS.md).

### Quick start

Install Python dependencies with `uv sync`, install frontend tooling with `bun install`, then run:

    make run

When the scaffold is present, `http://127.0.0.1:8000/health` should return `{"status":"ok"}`.

Useful targets:

    make install
    make css-watch
    make test
    make smoke-auth
    make upload-legacy-images

### Vercel deployment

This repository includes a Vercel entrypoint at `api/index.py` and a checked-in
`vercel.json`. The Vercel build runs:

    bun run build:css
    python scripts/prepare_vercel_static.py

That copies `app/static/` into `public/static/` so `/static/...` assets can be
served by Vercel directly, while all non-static routes are rewritten to the
FastAPI app.

`api/index.py` is intentionally tiny:

    from app.main import create_app
    app = create_app()

Vercel's Python runtime expects a module-level ASGI app object at that path.
Local development does not use this file; locally we run `app.main:create_app`
as a factory through Uvicorn. If Vercel deployment is ever removed, `api/index.py`
and `vercel.json` should be deleted together.

`.vercelignore` excludes local-only directories such as `data/` so recovered
media archives are not uploaded during deployment.

Implemented slices now include:

    /people
    /groups and /groups/{id}/semester-transfer
    /courses
    /users
    /registrations and /register/{token}
    /api/v1/mobile-card and /api/DigitalInternkort
    backend media proxy routes for private photos and documents

The current hosted Supabase project also expects these additive structures to exist:

    public.registrering
    public.nytt_personal
    public.personal.internkort_access_token_created_at
    storage buckets personnel-photos and personnel-documents

Legacy Azure media recovery is scripted in `scripts/download_legacy_azure_media.sh`.
It downloads the old Azure Blob `images` container into `data/legacy-images/`
and pulls the old App Service `files/` tree for `personal_fil` into
`data/legacy-personal-fil/`. The current live App Service directory exists but is
empty, so the `personal_fil` archive will only contain data if the old site still
has it when the script is run.

Recovered Azure images can be uploaded into the private Supabase
`personnel-photos` bucket with:

    make upload-legacy-images

The uploader is resumable. It compares the local archive in
`data/legacy-images/images/` with `storage.objects` and only uploads missing
object names. To restrict the upload to files referenced by `public.personal_bilde`,
run:

    uv run python scripts/upload_legacy_images_to_supabase.py --db-backed-only

To create a direct auth-backed admin user in the new system, run:

    uv run python scripts/bootstrap_auth_user.py \
      --email <email> \
      --username <username> \
      --password 'choose-a-password' \
      --display-name '<display-name>' \
      --role admin
