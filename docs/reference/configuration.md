# Configuration Reference

Configuration is loaded by `app/config.py` through Pydantic settings. Values come from environment variables and, in local development, `.env`.

Do not commit real secrets. The checked-in `.env.example` should contain names and safe placeholders only.

## Core Runtime

| Setting | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | required | Runtime environment: `development`, `test`, or `production`. Startup fails when it is omitted or invalid. |
| `APP_SECRET_KEY` | `change-me` | Signs web sessions, media tokens, mobile-card tokens, CSRF tokens, and Spotify OAuth state. In production it must be non-default and at least 32 characters. |
| `APP_PUBLIC_BASE_URL` | unset | Public base URL used in email links, media URLs, and OAuth redirects. Production requires an HTTPS origin without credentials, a path, query, or fragment. |
| `VOLUNTEER_PROSPECT_HMAC_SECRET` | unset | Active shared secret used to authenticate prospect requests from `samfunnetibergen`. Production requires at least 32 characters. |
| `VOLUNTEER_PROSPECT_HMAC_PREVIOUS_SECRET` | unset | Optional previous prospect-signing secret accepted temporarily during zero-downtime rotation. When set in production it requires at least 32 characters. |
| `VOLUNTEER_PROSPECT_MAX_BODY_BYTES` | `16384` | Maximum exact request-body size accepted by the volunteer-prospect endpoint. Larger bodies return `413` before JSON parsing. Keep this synchronized with the website proxy. |
| `VOLUNTEER_PROSPECT_ROUTE_LIMIT` | `120` | Route-wide volunteer-prospect requests allowed per window. |
| `VOLUNTEER_PROSPECT_ROUTE_WINDOW_SECONDS` | `60` | Route-wide volunteer-prospect fixed-window duration. |
| `VOLUNTEER_PROSPECT_CLIENT_LIMIT` | `10` | Volunteer-prospect requests allowed for one opaque client key per window. |
| `VOLUNTEER_PROSPECT_CLIENT_WINDOW_SECONDS` | `600` | Per-client volunteer-prospect fixed-window duration. |
| `VOLUNTEER_PROSPECT_EMAIL_LIMIT` | `3` | Volunteer-prospect requests allowed for one normalized email per window. |
| `VOLUNTEER_PROSPECT_EMAIL_WINDOW_SECONDS` | `3600` | Per-email volunteer-prospect fixed-window duration. |
| `LOG_LEVEL` | `INFO` | Application log level. |
| `DEV_ADMIN_EMAIL` | unset | Development-harness admin email. Refused unless `APP_ENV=development`. |
| `DEV_ADMIN_PASSWORD` | unset | Development-harness admin password. Refused unless `APP_ENV=development`. |

## Database and Supabase

| Setting | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | unset | SQLAlchemy connection string for Supabase Postgres. |
| `DATABASE_USE_NULL_POOL` | `false` | Use SQLAlchemy `NullPool`; recommended for Vercel/serverless. |
| `DATABASE_POOL_SIZE` | `5` | Local pooled connection count when not using `NullPool`. |
| `DATABASE_MAX_OVERFLOW` | `5` | Extra local pooled connections. |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `10` | How long to wait for a pooled connection. |
| `DATABASE_POOL_RECYCLE_SECONDS` | `1800` | Connection recycle interval. |
| `SUPABASE_URL` | unset | Supabase project URL for Auth APIs. |
| `SUPABASE_SECRET_KEY` | unset | Supabase secret/service key for backend Auth operations. |

## Storage

| Setting | Default | Purpose |
| --- | --- | --- |
| `AZURE_BLOB_CONNECTION_STRING` | unset | Enables Azure Blob photo storage and signed URLs. Required for media storage. |
| `AZURE_BLOB_ACCOUNT_NAME` | unset | Optional explicit account name for Azure photo SAS generation. |
| `AZURE_BLOB_ACCOUNT_KEY` | unset | Optional explicit account key for Azure photo SAS generation. |
| `AZURE_PHOTO_CONTAINER` | `images` | Azure Blob container for photos. |
| `PHOTO_UPLOAD_MAX_BYTES` | `41943040` | Maximum uploaded photo size. |
| `PHOTO_MAX_DIMENSION` | `2048` | Maximum processed photo dimension. |
| `PHOTO_DEFAULT_SIZE` | `512` | Default served photo size. |

When `APP_ENV=development` and Azure is not configured, the local harness
stores photos under `.devdata/photos/`.

## Email

The app accepts both current `SMTP_*` names and legacy `EMAIL_*` or `Email__*` aliases for several settings.

| Setting | Default | Purpose |
| --- | --- | --- |
| `SMTP_SERVER` | unset | SMTP host. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_SENDER_NAME` | `Det Akademiske Kvarter` | Display name in outbound email. |
| `SMTP_SENDER_EMAIL` | unset | Sender email address. |
| `SMTP_ACCOUNT` | unset | SMTP username/account. |
| `SMTP_PASSWORD` | unset | SMTP password. |
| `SMTP_USE_STARTTLS` | `true` | Whether to start TLS before login. |

When `APP_ENV=development` and `SMTP_SERVER` is unset, outbound HTML is written
to `.devdata/outbox/` and links are logged.

## Spotify and Now Playing

| Setting | Default | Purpose |
| --- | --- | --- |
| `SPOTIFY_CLIENT_ID` | unset | Spotify OAuth client id. |
| `SPOTIFY_CLIENT_SECRET` | unset | Spotify OAuth client secret. |
| `SPOTIFY_REFRESH_TOKEN` | unset | Fallback refresh token if no database token exists. |
| `NOW_PLAYING_CACHE_SECONDS` | `10.0` | Fresh cache window for now-playing data. |
| `NOW_PLAYING_STALE_GRACE_SECONDS` | `30.0` | Grace window for serving stale data during refresh failure. |

## Sessions, Caches, and Mobile-card Limits

| Setting | Default | Purpose |
| --- | --- | --- |
| `SESSION_COOKIE_NAME` | `kvarteret_session` | Web admin session cookie name. |
| `SESSION_TTL_HOURS` | `12` | Web session lifetime. |
| `SESSION_CACHE_TTL_SECONDS` | `300` | In-process session cache lifetime. |
| `PENDING_VOLUNTEER_APPLICATIONS_CACHE_TTL_SECONDS` | `30` | Pending application count cache lifetime. |
| `VOLUNTEER_DETAIL_CACHE_TTL_SECONDS` | `300` | Volunteer detail cache lifetime. |
| `ADMIN_ACCOUNTS_CACHE_TTL_SECONDS` | `60` | Admin account lookup cache lifetime. |
| `MOBILE_CARD_ACCESS_CODE_TTL_MINUTES` | `10` | Access-code lifetime. |
| `MOBILE_CARD_ACCESS_CODE_COOLDOWN_SECONDS` | `60` | Cooldown before sending/reusing another code. |
| `MOBILE_CARD_ACCESS_CODE_REQUEST_LIMIT` | `5` | Request limit per window/source. |
| `MOBILE_CARD_ACCESS_CODE_REQUEST_WINDOW_SECONDS` | `300` | Access-code request window. |
| `MOBILE_CARD_SESSION_ATTEMPT_LIMIT` | `5` | Failed session attempt limit. |
| `MOBILE_CARD_SESSION_ATTEMPT_WINDOW_SECONDS` | `600` | Failed session attempt window. |
| `MOBILE_CARD_SESSION_TTL_DAYS` | `90` | Signed mobile-card session lifetime. |
| `MOBILE_CARD_SESSION_RENEWAL_THRESHOLD_DAYS` | `30` | Threshold for returning a renewed session token. |

## Feedback and Review Bypass

| Setting | Default | Purpose |
| --- | --- | --- |
| `LINEAR_API_KEY` | unset | Linear API key used to create feedback issues. |
| `LINEAR_TEAM_ID` | unset | Linear team where feedback issues are created. |
| `LINEAR_PROJECT_ID_PERSONAL` | unset | Linear project for Personalplattformen feedback. |
| `LINEAR_PROJECT_ID_INTERNBEVIS` | unset | Linear project for internbevis app feedback. |
| `LINEAR_PROJECT_ID_NETTSIDE` | unset | Linear project for kvarteret.no feedback. |
| `LINEAR_STATE_ID_TRIAGE` | unset | Legacy Linear triage state setting. New feedback issues let Linear assign triage/default state. |
| `REVIEW_BYPASS_ENABLED` | `false` | Enables the app-store review bypass path for mobile-card review. |
| `REVIEW_BYPASS_EMAIL` | unset | Review bypass email. |
| `REVIEW_BYPASS_TOKEN` | unset | Review bypass token. |

The review bypass exists for app-store review compatibility. Keep it disabled unless the deployed mobile release flow requires it.
