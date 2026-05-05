# External Systems

This page documents third-party systems used by `kvarteret-personal` and related systems in scope.

## Direct Dependencies of `kvarteret-personal`

| System | Used for | Code owner path | Data direction |
| --- | --- | --- | --- |
| Supabase Postgres | Personnel data, web sessions, event schema, registration data, Spotify token storage | `app/db`, repositories, `migrations/` | read/write |
| Supabase Auth | Admin account lifecycle, login bridge, password setup | `app/auth/supabase_auth.py` | read/write over HTTP |
| Supabase Storage | Personnel documents, optional photo storage, bucket maintenance | `app/infrastructure/storage/service.py` | read/write over Storage API |
| Azure Blob Storage | Legacy-compatible personnel photo storage when configured | `app/infrastructure/storage/service.py` | read/write and signed read URLs |
| Spotify Web API | Shared now-playing state and OAuth refresh token exchange | `app/domain/spotify/now_playing.py` | OAuth and read |
| SMTP provider | Mobile-card access codes and onboarding/application email | `app/infrastructure/email/smtp.py` | outbound email |
| Slack Incoming Webhook | Feedback submissions from the admin UI | `app/domain/feedback/service.py` | outbound webhook |
| Vercel | Runtime for the FastAPI ASGI app and static asset serving | `api/index.py`, `vercel.json` | deployment/runtime |

## Supabase

Supabase Postgres is the primary database. The app connects through SQLAlchemy Core using `DATABASE_URL`. In serverless production, `DATABASE_USE_NULL_POOL=true` avoids keeping idle SQLAlchemy pool connections alive across Vercel invocations.

Supabase Auth is not the mobile-card auth provider. It is used for admin-user lifecycle and password flows. The app bridges old auth state into Supabase Auth and stores web sessions separately.

Supabase Storage is used for private documents and can be used for personnel photos when Azure photo credentials are absent. Buckets default to `personnel-photos` and `personnel-documents`.

## Azure Blob Storage

Azure Blob Storage is used for personnel photos when `AZURE_BLOB_CONNECTION_STRING` is configured. The default container is `images`.

The storage adapter deliberately hides this split. Callers ask for photo operations; the adapter chooses Azure first when configured, otherwise Supabase Storage.

## Spotify

Spotify powers the now-playing feature. Admins connect the shared account through `/spotify/login` and `/spotify/callback`. The refresh token is stored in the `integration_tokens` table when the migration is available; `SPOTIFY_REFRESH_TOKEN` can act as a fallback.

The public endpoint is `GET /api/now-playing`. It never exposes Spotify tokens.

## SMTP

SMTP is required for flows that send email:

- mobile-card access codes
- volunteer application invitations and profile completion email
- admin account onboarding/password setup

If SMTP is not configured, email-sending paths fail with a configuration error. The access-code API still avoids email enumeration by returning accepted for unknown or duplicate people.

## Slack Incoming Webhooks

The feedback panel posts to a Slack Incoming Webhook configured by `SLACK_FEEDBACK_WEBHOOK_URL`. The service validates category, email, message length, and page length before posting.

## Vercel

Vercel loads `api/index.py` and expects a module-level ASGI app. The build prepares static assets by copying `app/static/` to `public/static/`, while `vercel.json` routes non-static requests to the FastAPI function.

Do not store secrets in `NEXT_PUBLIC_*` variables or checked-in files. Use Vercel environment variables for production secrets.

## Related Sibling-System Dependencies

These systems are not direct runtime dependencies of `kvarteret-personal`, but they affect the system map:

| System | Used by | Purpose |
| --- | --- | --- |
| PostHog | `samfunnetibergen`, `kvarteret-internbevis-rn` | analytics and funnel events |
| Sanity | `samfunnetibergen` | recruitment/content data |
| Expo/EAS | `kvarteret-internbevis-rn` | mobile builds, updates, release workflows |
| Firebase App Distribution | `kvarteret-internbevis-rn` | installable preview binaries |
| StudentBergen | `frontend-eventside` workflow context | external event publication and organization API context |

When documenting a failure or integration change, be explicit about whether the dependency is direct to `kvarteret-personal` or belongs to a sibling repo.
