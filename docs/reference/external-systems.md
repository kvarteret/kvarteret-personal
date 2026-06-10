# External Systems

This page documents third-party systems used by `kvarteret-personal` and related systems in scope.

## Direct Dependencies of `kvarteret-personal`

| System | Used for | Code owner path | Data direction |
| --- | --- | --- | --- |
| Supabase Postgres | Personnel data, web sessions, registration data, Spotify token storage | `app/db`, repositories, `migrations/` | read/write |
| Supabase Auth | Admin account lifecycle, login bridge, password setup | `app/auth/supabase_auth.py` | read/write over HTTP |
| Azure Blob Storage | Personnel photo storage | `app/infrastructure/storage/service.py` | read/write and signed read URLs |
| Spotify Web API | Shared now-playing state and OAuth refresh token exchange | `app/domain/spotify/now_playing.py` | OAuth and read |
| SMTP provider | Mobile-card access codes and onboarding/application email | `app/infrastructure/email/smtp.py` | outbound email |
| Linear | Feedback submissions from the admin UI and public feedback API | `app/domain/feedback/service.py` | outbound GraphQL API |
| Vercel | Runtime for the FastAPI ASGI app and static asset serving | `api/index.py`, `vercel.json` | deployment/runtime |

## Supabase

Supabase Postgres is the primary database. The app connects through SQLAlchemy Core using `DATABASE_URL`. In serverless production, `DATABASE_USE_NULL_POOL=true` avoids keeping idle SQLAlchemy pool connections alive across Vercel invocations.

Supabase Auth is not the mobile-card auth provider. It is used for admin-user lifecycle and password flows. The app bridges old auth state into Supabase Auth and stores web sessions separately.

## Azure Blob Storage

Azure Blob Storage is the only supported media backend for personnel photos. Configure `AZURE_BLOB_CONNECTION_STRING`; the default container is `images`.

## Spotify

Spotify powers the now-playing feature. Admins connect the shared account through `/spotify/login` and `/spotify/callback`. The refresh token is stored in the `integration_tokens` table when the migration is available; `SPOTIFY_REFRESH_TOKEN` can act as a fallback.

The public endpoint is `GET /api/now-playing`. It never exposes Spotify tokens.

## SMTP

SMTP is required for flows that send email:

- mobile-card access codes
- volunteer application invitations and profile completion email
- admin account onboarding/password setup

If SMTP is not configured, email-sending paths fail with a configuration error. The access-code API still avoids email enumeration by returning accepted for unknown or duplicate people.

## Linear

The feedback panel and `POST /api/v1/feedback/` create Linear issues through the GraphQL API. The service validates category, email, message length, and page length before creating an issue.

New issues require `LINEAR_API_KEY`, `LINEAR_TEAM_ID`, and the relevant `LINEAR_PROJECT_ID_*`. The service does not force a workflow state; Linear assigns triage/default state for the target team. If any required value is missing or Linear rejects the request, the form reports a delivery error instead of showing a false success message.

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
| StudentBergen | retired `frontend-eventside` workflow context | historical external event publication and organization API context |

When documenting a failure or integration change, be explicit about whether the dependency is direct to `kvarteret-personal` or belongs to a sibling repo.
