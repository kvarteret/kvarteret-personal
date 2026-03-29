# Build the FastAPI, HTMX, Tailwind, Supabase, and PostgREST replacement for Kvarteret Personal

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md`.

## Purpose / Big Picture

After this change, Kvarteret will have a new public-safe codebase that replaces the old Angular frontend and ASP.NET backend with a FastAPI server-rendered application. Admins will be able to log in, manage people, groups, courses, files, photos, and registrations through a modern HTML interface built with HTMX and Tailwind. The Digitalt Internkort app will continue to work during the transition through legacy compatibility endpoints, while a new English, more REST-like mobile API is introduced beside them.

The first implemented slice in this repository is the foundation: planning files, project scaffold, health endpoint, placeholder admin shell, legacy password verification prototype, and private signed-photo URL prototype. A novice should be able to start the server, open the shell, run tests, and inspect the prototypes before the full domain implementation lands.

## Progress

- [x] (2026-03-13 08:59Z) Inspected the empty target repository and confirmed it contained no application code.
- [x] (2026-03-13 08:59Z) Read the legacy frontend, backend, RN app contract, and Supabase project state to identify real source-of-truth behavior.
- [x] (2026-03-13 08:59Z) Confirmed the hosted Supabase project already contains the copied personnel schema and legacy `aspnet*` tables, but `auth.users` is empty and no migrations are tracked.
- [x] (2026-03-13 08:59Z) Confirmed `personal.brukerkonto` is unused in current data and must not be the basis of the new auth model.
- [x] (2026-03-13 08:59Z) Chose the major architectural direction: English public API, private signed photo delivery, rolling auth bridge, and dual mobile API during migration.
- [x] (2026-03-13 10:15Z) Created `/PLANS.md` and this plan file in the repository.
- [x] (2026-03-13 10:15Z) Initialized Python and npm tooling and installed FastAPI, SQLAlchemy, Supabase, pytest, and Tailwind dependencies.
- [x] (2026-03-13 10:28Z) Scaffolded the FastAPI app, templates, Tailwind entrypoint, health endpoint, placeholder dashboard, login page, and legacy/mobile API placeholders.
- [x] (2026-03-13 10:28Z) Implemented the ASP.NET Identity password verification prototype and tests, including a parser check against a deterministic synthetic admin hash fixture.
- [x] (2026-03-13 10:28Z) Implemented the signed-photo URL prototype and tests through a dedicated storage service.
- [x] (2026-03-13 10:35Z) Added prototype coverage for both the new English mobile-card API and the temporary legacy Internkort adapter.
- [x] (2026-03-13 10:54Z) Applied the additive auth/session tables to the hosted Supabase project and confirmed `user_accounts`, `group_admin_memberships`, `web_sessions`, and `auth_migration_events` exist.
- [x] (2026-03-13 10:54Z) Implemented session-based web auth scaffolding, signed session cookies, protected routes, and the first-login legacy-to-Supabase bridge service with unit and route tests.
- [x] (2026-03-13 11:44Z) Added a repository `Makefile` with stable top-level commands for install, CSS build/watch, app startup, and tests.
- [x] (2026-03-13 13:04Z) Replaced the placeholder people page with a real database-backed people list/detail slice, including person documents from `personal_fil`.
- [x] (2026-03-13 13:04Z) Added database-backed read-only groups and courses list/detail slices with protected English JSON APIs and HTML pages.
- [x] (2026-03-13 13:04Z) Standardized the backend configuration on `SUPABASE_SECRET_KEY` and removed legacy Supabase key naming from the codebase.
- [x] (2026-03-13 14:06Z) Fixed the local `DATABASE_URL` to use the Supabase session pooler and verified live SQLAlchemy reads against the hosted project.
- [x] (2026-03-13 14:06Z) Implemented the advanced search service, protected English search API, and a first HTML search page that ports the legacy set-logic.
- [x] (2026-03-13 14:06Z) Added an authenticated `GET /api/v1/auth/me` endpoint so the new backend exposes a clean auth identity contract.
- [x] (2026-03-13 16:24Z) Added live-auth operational scripts for direct user bootstrap and a real create-login-cleanup smoke test against hosted Supabase Auth.
- [x] (2026-03-13 16:24Z) Verified live web login end to end with `make smoke-auth`, then cleaned the temporary auth records back out of `auth.*` and `public.user_accounts`.
- [x] (2026-03-13 16:42Z) Added a protected admin-only users slice backed by `public.user_accounts`, with English JSON and HTML list/detail routes.
- [x] (2026-03-13 17:08Z) Replaced per-row Supabase signed photo URLs with backend media proxy URLs for people and documents, removing the main people-list latency spike.
- [x] (2026-03-13 17:28Z) Added an in-process authenticated-session cache in `SessionStore`, removing repeated per-request session database lookups inside a worker.
- [x] (2026-03-13 17:36Z) Added an internal PostgREST client and moved simple group/course list reads onto it, while keeping complex/auth/search flows on direct SQL.
- [x] (2026-03-13 18:09Z) Removed all remaining inline SQL from repository code and rewrote the database layer onto SQLAlchemy Core table metadata and expressions.
- [x] (2026-03-13 19:45Z) Added the additive registration/mobile migration, applied it to the hosted Supabase project, and created the private `personnel-photos` and `personnel-documents` storage buckets.
- [x] (2026-03-13 20:05Z) Implemented real photo/document upload and delete paths backed by Supabase Storage and surfaced them in both the English API and the HTML people detail page.
- [x] (2026-03-13 20:18Z) Implemented the registration flow backed by `registrering` and `nytt_personal`, including admin invite/approve pages and a public `/register/{token}` submission page.
- [x] (2026-03-13 20:26Z) Replaced the mobile-card prototype with a real database-backed Internkort flow that stores OTP codes on `public.personal`, issues signed session tokens, and keeps the legacy adapter path.
- [x] (2026-03-13 20:34Z) Implemented semester-transfer preview/apply flows in both the English API and the HTML group workflow.
- [x] (2026-03-13 20:42Z) Repaired the live auth smoke cleanup script for Supabase auth schema type mismatches and re-verified `make smoke-auth` end to end after the new migration landed.
- [x] (2026-03-13 20:55Z) Added `architecture.md` to document the implemented runtime architecture, data flows, and remaining cutover gaps.
- [x] (2026-03-13 12:40Z) Recovered the legacy Azure Blob `images` container locally into `data/legacy-images` with 5,853 files totaling 2.4 GB; 8 transfers failed and should be retried or inspected from the AzCopy log.
- [x] (2026-03-13 12:40Z) Confirmed the old `personal_fil` path is the App Service filesystem at `site/wwwroot/files` on `personaldatabasen-api`, saved a reusable retrieval script, and verified the current live directory is empty.
- [x] (2026-03-13 13:22Z) Added a resumable legacy-image uploader that compares `data/legacy-images/images/` against `storage.objects` and uploads missing files into the private `personnel-photos` bucket.
- [x] (2026-03-13 13:39Z) Uploaded the recovered Azure image archive into Supabase `personnel-photos`, retried transient TLS failures, and verified the final bucket count at 5,853 objects.
- [x] (2026-03-13 14:05Z) Added a Vercel deployment entrypoint, build-time static export, and rewrite configuration so the FastAPI app can be deployed as a Vercel Python function.
- [x] (2026-03-13 14:12Z) Added `.vercelignore` after the first production deploy failed by trying to upload the local 2.4 GB `data/` archive.
- [x] (2026-03-13 14:23Z) Hardened settings parsing to strip whitespace from string and boolean env values after the Vercel runtime crashed on `REVIEW_BYPASS_ENABLED=false\\n`.
- [x] (2026-03-13 14:31Z) Reworked the people directory to load ten results at a time with HTMX active search and infinite scroll partials.
- [x] (2026-03-13 14:31Z) Switched production/serverless SQLAlchemy engine creation to `NullPool` to avoid exhausting the Supabase session pooler on Vercel.
- [x] (2026-03-13 14:31Z) Redeployed the team-owned Vercel project in Stockholm (`arn1`) and verified `/health` plus a fresh media-token photo request on `kvarteret-personal-three.vercel.app`.
- [x] (2026-03-13 15:22Z) Profiled the localhost people detail route and confirmed the remaining latency floor is database round trips to Supabase, not template rendering or image work.
- [x] (2026-03-13 15:22Z) Collapsed `PeopleService.get_person_detail()` from five serial queries to one SQLAlchemy query with JSON aggregates, and added a short-lived in-process person-detail cache with write-path invalidation.
- [x] (2026-03-13 15:36Z) Replaced the ad hoc per-process caches with a reusable TTL cache and extended the default read-cache lifetime for authenticated sessions and person detail reads to five minutes.
- [x] (2026-03-13 15:44Z) Fixed people-directory multi-word search in the PostgREST path by tokenizing the query and requiring each token to match somewhere in the record.
- [x] (2026-03-13 16:02Z) Added ranked fuzzy people search on Supabase Postgres using `pg_trgm`, while keeping the plain unfiltered directory path on PostgREST.
- [ ] Finish the Vercel cutover under the Kvarteret team account (completed: Vercel entrypoint/config, initial project link under the current scope, env-parsing fix for newline-polluted variables; remaining: reauthenticate the CLI, move or recreate the project under the requested Kvarteret scope, repopulate env vars there, and redeploy).
- [ ] Create initial database migration baseline and new auth/session tables (completed: additive auth/session migration scaffold, Alembic config, and live auth/session tables; remaining: baseline the existing public schema and apply safely on a Supabase development branch).
- [ ] Implement English admin routes and explicit response models for the remaining CRUD mutations (completed: people/groups/courses/users/search/auth plus registration, photo/document writes, mobile-card, and semester transfer; remaining: broader create/update/delete parity for groups, courses, and users).
- [ ] Add RLS, CSRF, and final production hardening before cutover (completed: structured response models, backend-only media access, mobile-card cooldown/rate limiting, and contract tests; remaining: RLS and CSRF).

## Surprises & Discoveries

- Observation: The Supabase project is not empty. It already contains live-looking data in `public.personal`, `public.historie`, `public.grupper`, `public.personal_bilde`, and the legacy `public.aspnet*` identity tables.
  Evidence: Research queries showed `public.personal` with 10044 rows, `public.historie` with 27908 rows, and `public.aspnetusers` with 66 rows.

- Observation: Supabase Auth has not been adopted yet.
  Evidence: `select count(*) as auth_users from auth.users;` returned `0`.

- Observation: The old backend already contains a hardcoded App Store review bypass for Internkort and the old API often mutates state on `GET`.
  Evidence: `DigitalInternkortService.cs` defines a hardcoded review email and token; legacy endpoints include `GET /api/Grupper/Remove/{id}` and `GET /api/Personal/Remove/{id}`.

- Observation: The copied legacy admin password hash uses ASP.NET Identity v3 format with SHA-512, 100000 iterations, 16-byte salt, and 32-byte subkey.
  Evidence: The parser test against the real `admin` hash decodes marker `1`, PRF `2`, iterations `100000`, salt length `16`, and subkey length `32`.

- Observation: The app root can no longer be treated as a public smoke-check page once the auth guard is enabled.
  Evidence: the `GET /` test had to be updated from rendering the dashboard directly to asserting a `303` redirect to `/login`.

- Observation: `personal_fil` is mostly a person-document feature for PDFs, not a general object store.
  Evidence: the current dataset contains `88` rows in `public.personal_fil`, of which `79` are `pdf`, `9` are `jpg`, and `85` are group-scoped through `gruppekobling`.

- Observation: The current local `DATABASE_URL` value in `.env` is not usable for a live SQLAlchemy smoke test from this machine.
  Evidence: a direct `PeopleService` query failed with `socket.gaierror: [Errno 8] nodename nor servname provided, or not known` for the configured Postgres host.

- Observation: The repaired pooler connection and configured `SUPABASE_SECRET_KEY` now allow live SQLAlchemy reads and real web-login smoke tests from this machine.
  Evidence: live people, search, and users queries succeeded against the hosted project, and `make smoke-auth` completed a real create-login-cleanup round trip.

- Observation: Hosted Supabase Auth admin user creation works with the configured key, but admin deletion through the SDK returned `403 User not allowed` during smoke cleanup.
  Evidence: the first live smoke run printed `LOGIN_OK ...` and then failed on `supabase_auth.errors.AuthApiError: User not allowed` from `delete_user`.

- Observation: Direct database cleanup against `auth.refresh_tokens`, `auth.sessions`, `auth.identities`, and `auth.users` is reliable for temporary smoke accounts.
  Evidence: after switching the smoke script to SQL cleanup and rerunning, `make smoke-auth` succeeded and a follow-up query showed only the expected retained auth user remained.

- Observation: The people list slowdown was dominated by synchronous per-row Storage URL signing, not by the SQL query itself.
  Evidence: `EXPLAIN ANALYZE` for the list query executed in about `0.546 ms`, while live app timings showed `people.list` at about `7127.6 ms` with per-row Storage signing versus `160.2 ms` without it.

- Observation: Repeated authenticated requests were paying roughly `213 ms` per request just to resolve the web session from Postgres.
  Evidence: a live timing against `load_authenticated_user_for_session()` measured `session.load_ms 212.8` before caching.

- Observation: A short-lived in-process session cache removes the repeated lookup cost inside a worker.
  Evidence: after the cache was added, live timings showed `session.load.1 215.5 ms` and `session.load.2 0.0 ms` for the same session id.

- Observation: The current repository no longer contains inline SQL query strings after the SQLAlchemy Core refactor.
  Evidence: `rg -n "\\btext\\(|bindparam\\(" app scripts tests` returned no matches after the refactor.

- Observation: The live auth smoke test is currently flaky at the Supabase Auth network layer, independent of the database-query refactor.
  Evidence: `make smoke-auth` intermittently fails in `supabase-py` user creation with `httpx.ConnectError: [SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC]`, after previously succeeding on the same code path.

- Observation: The hosted Supabase copy of the schema did not contain `registrering`, `nytt_personal`, or the mobile-card timestamp column yet, and Storage had no buckets.
  Evidence: `information_schema.columns` returned no rows for `registrering` and `nytt_personal`, and `select id from storage.buckets` returned an empty set before the additive migration.

- Observation: Supabase auth cleanup requires a string comparison on `auth.refresh_tokens.user_id`, even though the surrounding auth tables mostly use UUID columns.
  Evidence: `make smoke-auth` failed with `operator does not exist: character varying = uuid` until the cleanup script compared `auth_refresh_tokens.c.user_id` to `str(auth_user_id)`.

- Observation: The old `personal_fil` data path is the App Service filesystem on `personaldatabasen-api`, not Azure Blob Storage.
  Evidence: Kudu `api/vfs/site/wwwroot/` for the running app listed a `files` directory, while the `personaldatabasen` storage account only exposed `backups`, `directus`, `directuspersonal`, `extensions`, and `images`.

- Observation: The current live App Service `files` directory is empty, so there is no remaining `personal_fil` payload to recover from the running site.
  Evidence: Kudu `api/vfs/site/wwwroot/files/` returned `entries 0`, and the downloaded `api/zip/site/wwwroot/files/` archive contained `0` files.

- Observation: The recovered Azure image archive contains more files than the active `public.personal_bilde` references.
  Evidence: the local archive contains 5,853 files under `data/legacy-images/images/`, while `public.personal_bilde` currently contains 5,614 rows.

- Observation: The full Supabase image import completed, but the first large batch saw transient TLS and broken-pipe failures from the storage client.
  Evidence: the initial batch uploaded 5,824 files and left 19 failures with `DECRYPTION_FAILED_OR_BAD_RECORD_MAC` and `Broken pipe`; a retry cleared 18 of them and one final direct upload brought `storage.objects` to 5,853 rows.

- Observation: Vercel deployment needs an explicit Python function entrypoint and a static export step for `/static/...` assets.
  Evidence: the repository had no `.vercel` link, no `api/index.py`, and all CSS lived under `app/static/` rather than Vercel `public/`.

- Observation: Vercel deploys upload the working tree, not just tracked source files, unless `.vercelignore` excludes large local artifacts.
  Evidence: the first `vercel deploy --prod` failed with `File size (2583159055) is greater than 2 GiB` because the local `data/` archive was included.

- Observation: Vercel stored `REVIEW_BYPASS_ENABLED` with a trailing newline during the scripted env import, which crashed the Python app at import time.
  Evidence: Vercel runtime logs showed `ValidationError` for `review_bypass_enabled` with input value `false\\n`.

- Observation: The current local Vercel CLI session expired after the initial deployment work, even though the project link file remains on disk.
  Evidence: later `vercel whoami`, `vercel teams ls`, and `vercel env ls` calls returned `No existing credentials found`.

- Observation: The Supabase session pooler can be exhausted quickly from Vercel serverless requests when the SQLAlchemy engine keeps its own connection pool.
  Evidence: Vercel runtime logs during login showed `asyncpg.exceptions.InternalServerError: MaxClientsInSessionMode: max clients reached - in Session mode max clients are limited to pool_size`.

- Observation: The original `kvarteret-personal.vercel.app` alias still points at an older broken project, while the healthy Kvarteret team deployment owns `kvarteret-personal-three.vercel.app`.
  Evidence: alias assignment to `kvarteret-personal.vercel.app` failed with `already in use`, and `vercel inspect` for the team deployment listed `kvarteret-personal-three.vercel.app` as the production alias.

- Observation: The localhost people detail page was still slow after the earlier list and session optimizations because it chained multiple remote database round trips to Supabase.
  Evidence: warm timings showed `select 1` at about `52 ms`, session lookup at `0 ms` after cache warmup, and the old detail fetch at about `510 ms` warm because it executed five serial person-related queries.

- Observation: A single remote SQL query plus a short-lived local cache is enough to make repeated people detail loads effectively free inside one worker, but the first uncached hit still cannot beat the physical database round-trip budget.
  Evidence: after the refactor, the first detail fetch for person `10016` was about `367 ms`, while repeated cached fetches in the same process measured `0.0 ms`.

- Observation: Extending the read-cache TTL to five minutes materially improves normal operator navigation because the warmed route stays fast across repeated opens instead of expiring after a few seconds.
  Evidence: after extending both the session and person-detail caches to `300` seconds, repeated `/people/10016` requests stayed around `1-5 ms` in-process instead of falling back to the remote query path on short revisits.

- Observation: The people-directory bug where `martin kleiven` returned no match while `kleiven` did was caused by the PostgREST list filter only checking the full query string against `fornavn` and `etternavn` separately.
  Evidence: a direct SQL full-name query matched `Martin Kleiven`, while the live `PeopleService.list_people_page()` PostgREST path returned `[]` until the filter was changed to build `and=(or(...martin...),or(...kleiven...))`.

- Observation: Ranked fuzzy search works well for name typos and multi-word inputs, but the live query latency from localhost is still bounded by the remote Supabase round trip.
  Evidence: after moving search onto `pg_trgm`, queries like `martn kleiven` and `martin kleven` both returned `Martin Kleiven`, while warm localhost timings for the remote ranked query remained around `500 ms`.

## Decision Log

- Decision: All new public JSON APIs will use English route names and English field names in `snake_case`.
  Rationale: The user explicitly requested an English API, while the database can remain Norwegian internally for migration safety.
  Date/Author: 2026-03-13 / Codex

- Decision: Personnel photos will live in a private Supabase Storage bucket named `personnel-photos`, and personnel documents will live in `personnel-documents`.
  Rationale: The repository is public and these names describe the bucket contents clearly.
  Date/Author: 2026-03-13 / Codex

- Decision: The new mobile API will be added beside the old Internkort endpoints, and the legacy endpoints will be thin adapters over the new service layer.
  Rationale: This keeps one source of truth while allowing a controlled RN transition.
  Date/Author: 2026-03-13 / Codex

- Decision: Web admin authentication will use a rolling bridge from `public.aspnetusers` into Supabase Auth.
  Rationale: This avoids forcing every existing user through an immediate password reset.
  Date/Author: 2026-03-13 / Codex

- Decision: The first migration committed in this repository is an additive auth/session migration scaffold, not a full baseline of the copied public schema.
  Rationale: The repository needed runnable code and tracked migration structure immediately, but applying a true baseline safely still depends on a Supabase development branch workflow.
  Date/Author: 2026-03-13 / Codex

- Decision: The initial working login milestone uses unit-tested bridge services plus protected HTML routes, but does not yet attempt an end-to-end live login against Supabase Auth from local tests.
  Rationale: The service layer is now concrete and testable, but deterministic local tests should not depend on hosted credentials or mutate real auth users on every run.
  Date/Author: 2026-03-13 / Codex

- Decision: The new `personnel-documents` bucket path should preserve the old disk layout semantics as `{person_id}/{filename}`.
  Rationale: The old backend stored files on disk under `files/{personId}/{filename}` while keeping only metadata in `personal_fil`. Reusing that shape makes migration scripts simpler and keeps document paths understandable.
  Date/Author: 2026-03-13 / Codex

- Decision: Local database access should use the Supabase session pooler connection string rather than the direct host.
  Rationale: The direct host exposed only IPv6 from this environment, while the session pooler provides a working IPv4-accessible path and is the recommended connection mode in Supabase docs for most tooling.
  Date/Author: 2026-03-13 / Codex

- Decision: The live auth smoke test should create and remove temporary users through the application plus direct SQL cleanup, rather than relying on `supabase-py` admin deletion.
  Rationale: End-to-end login validation is important, but the configured key produced a `403 User not allowed` on SDK deletion even though creation and sign-in worked. Direct cleanup keeps the smoke test deterministic and leaves the hosted project clean.
  Date/Author: 2026-03-13 / Codex

- Decision: The next auth-facing admin slice after login is `/users`, backed directly by `public.user_accounts`, and it is admin-only.
  Rationale: Once live auth works, admins need visibility into which accounts have been migrated or created directly. This is the new backend’s actual auth state, so surfacing it early provides operational leverage for the rest of the migration.
  Date/Author: 2026-03-13 / Codex

- Decision: Backend-rendered people and document links should use backend media proxy URLs with short-lived app-signed tokens, not per-row Supabase signed URLs.
  Rationale: The signed-URL generation was the main source of list-page latency. App-signed media URLs keep the bucket private while moving Storage fetches out of the HTML generation path.
  Date/Author: 2026-03-13 / Codex

- Decision: Session resolution should use a short-lived in-process cache keyed by session id, with invalidation on logout.
  Rationale: The middleware needs authenticated user data on every protected request, but paying a live database hit for each request was avoidable and materially slow. A short cache gives most of the win without redesigning the auth cookie format yet.
  Date/Author: 2026-03-13 / Codex

- Decision: PostgREST should be used only for simple table reads at this stage, specifically the groups and courses list endpoints.
  Rationale: It reduces boilerplate where the query shape is a direct table scan with filters and ordering. Complex views such as auth, people detail, search, and other multi-query flows remain clearer and safer on direct SQL for now.
  Date/Author: 2026-03-13 / Codex

- Decision: The repository should use SQLAlchemy Core expressions and shared table metadata for direct database access, and should not use inline SQL strings.
  Rationale: The direct SQL strings were harder to maintain, inconsistent with the requested direction, and made type mismatches easier to introduce. Core expressions keep the query layer typed and composable while preserving explicit control over SQL shape.
  Date/Author: 2026-03-13 / Codex

- Decision: People detail should be built from one SQLAlchemy query with Postgres JSON aggregates and then cached briefly in-process, rather than issuing multiple serial child-table queries on every request.
  Rationale: On localhost against the hosted Supabase database, the query floor is set mostly by network and connection latency. Reducing the request from five round trips to one meaningfully lowers first-hit latency, and the short-lived cache gets repeated admin navigation under the desired threshold without changing the API contract.
  Date/Author: 2026-03-13 / Codex

- Decision: The repository should use a reusable TTL read cache with a five-minute default for authenticated sessions and person-detail reads.
  Rationale: The app is read-heavy during normal admin navigation, and the user explicitly wanted a real read cache with longer TTL. Five minutes is long enough to keep common back-and-forth navigation fast, while still short enough that occasional stale reads are bounded and explicit write-path invalidation keeps person updates coherent.
  Date/Author: 2026-03-13 / Codex

- Decision: PostgREST-backed people search should tokenize multi-word queries and require every token to match at least one searchable field.
  Rationale: This preserves the low-boilerplate PostgREST list path while restoring expected full-name search behavior such as `martin kleiven` and names with multiple surname parts.
  Date/Author: 2026-03-13 / Codex

- Decision: Ranked fuzzy people search should run directly on Supabase Postgres with `pg_trgm`, while the plain unfiltered people directory should stay on PostgREST.
  Rationale: PostgREST is fine for simple list retrieval, but ranked fuzzy matching needs direct query control for token logic and score ordering. Splitting the paths keeps the list code simple and enables typo-tolerant ranking for interactive search.
  Date/Author: 2026-03-13 / Codex

- Decision: The registration flow should use real `public.registrering` and `public.nytt_personal` tables in Supabase, rather than inventing a renamed English schema.
  Rationale: The user explicitly asked to think about the old handover flow, and these table names are already part of the legacy mental model and migration story. The public API stays English while the database stays additive and migration-safe.
  Date/Author: 2026-03-13 / Codex

- Decision: The new mobile-card session token is a signed stateless application token rather than a database row.
  Rationale: The mobile session only needs to prove the previously verified person id for a short period. A signed token keeps the service simple, avoids another table, and lets `/api/v1/mobile-card/me` always rebuild the current card from live data.
  Date/Author: 2026-03-13 / Codex

- Decision: Legacy media recovery should be scripted in-repo using Azure CLI plus AzCopy for blob images and Kudu zip download for `personal_fil`.
  Rationale: The old system stored images in Azure Blob `images` and documents on the App Service filesystem. Capturing both retrieval paths in one script makes the handover repeatable and avoids manual secret handling.
  Date/Author: 2026-03-13 / Codex

- Decision: The Supabase image import should be resumable and compare local files against both `storage.objects` and `public.personal_bilde`.
  Rationale: The recovered archive is larger than the live database reference set, and a retry-safe importer is required for a 2.4 GB batch upload into a private bucket.
  Date/Author: 2026-03-13 / Codex

- Decision: Vercel should serve `/static/...` from `public/static` while rewriting all non-static paths to a single FastAPI function at `api/index.py`.
  Rationale: This keeps the deployment model simple, avoids routing static requests through Python, and matches the existing template URLs without rewriting the app.
  Date/Author: 2026-03-13 / Codex

- Decision: The application settings layer should strip surrounding whitespace from env-provided strings and booleans before validation.
  Rationale: Deployment platforms and CLI-based env import flows can preserve trailing newlines, and the app should not fail to boot because of that formatting artifact.
  Date/Author: 2026-03-13 / Codex

- Decision: The people directory should render ten records per page and use HTMX for active search plus infinite scroll, instead of rendering the first fifty records server-side.
  Rationale: This materially reduces initial page cost, matches the requested behavior, and keeps the web UI responsive on Vercel while still preserving server-rendered HTML.
  Date/Author: 2026-03-13 / Codex

- Decision: Production and Vercel serverless deployments should create the SQLAlchemy async engine with `NullPool`.
  Rationale: The app already sits behind the Supabase session pooler, and adding an application-side pool on short-lived serverless workers creates unnecessary connection pressure and caused real login failures.
  Date/Author: 2026-03-13 / Codex

## Outcomes & Retrospective

The repository now covers the core operational slices instead of just the scaffold. It carries its own planning rules and execution document, ships a runnable FastAPI app with protected routes, has a working `/health` endpoint, includes passing tests for auth and media prototypes, contains a concrete login bridge service plus live auth/session support tables in Supabase, and now has real people, groups, courses, users, registrations, mobile-card, and semester-transfer flows in both JSON and HTML. Live web login has been re-verified end to end against hosted Supabase Auth after the new migration landed. The largest people-list latency regression has been removed by switching from per-row Supabase signed URLs to backend media proxy URLs, repeated authenticated requests no longer pay a live session lookup on every request inside a worker, and the direct database layer now uses SQLAlchemy Core instead of inline SQL strings. The remaining work is narrower: baseline the existing schema cleanly, then finish the last hardening and parity gaps such as RLS, CSRF, and broader create/update/delete coverage for every admin domain.

The scaffold also now has a top-level `Makefile`, which removes guesswork for the basic developer workflow and gives novices one command path for starting and testing the project.

The repository also now contains a repeatable legacy-media recovery script. It successfully downloaded the blob-backed image archive locally, and it confirmed that the currently running App Service no longer contains any `personal_fil` payload in `site/wwwroot/files`. If those files still exist anywhere, the next recovery target is an older app backup rather than the live site.

The legacy image archive has now also been imported into the private Supabase `personnel-photos` bucket. The final bucket count matches the recovered local archive at 5,853 objects. The current live `public.personal_bilde` table references 5,614 of those files, so the bucket now preserves both the active DB-backed photo set and additional orphaned historical objects recovered from Azure.

## Context and Orientation

The working directory is `/Users/kluvin/dev/kvarteret/kvarteret-personal`. The legacy frontend is in `../personaldatabase_frontend`, the legacy ASP.NET backend is in `../Personaldatabase_Backend`, and the React Native mobile app is in `../kvarteret-internbevis-rn`.

The new codebase lives under `/app`. `/app/main.py` will define the FastAPI application factory. `/app/config.py` will load settings from the environment. `/app/auth/` will hold session-cookie code, role loading, Supabase Auth integration, and legacy ASP.NET password verification. `/app/api/` will hold JSON routes. `/app/web/` will hold HTML routes. `/app/templates/` and `/app/static/` will hold the user interface.

The first risky prototype is the legacy password verifier. In this repository, that means Python code that can validate the copied ASP.NET Identity password hashes stored in `public.aspnetusers.passwordhash`.

The second risky prototype is private signed-photo delivery. In this repository, that means code that can mint a short-lived Supabase Storage signed URL for a path like `abc123.jpg` inside the future `personnel-photos` bucket.

The current login path uses a signed session cookie. In this repository, that means the browser stores a signed opaque session id, while the actual session record lives in `public.web_sessions`. The middleware in `app/main.py` reads that cookie and loads the authenticated user into `request.state`.

## Plan of Work

First, scaffold the repository so it becomes runnable: create `.gitignore`, Tailwind scripts, the FastAPI app package, placeholder templates, and a health route. Then add isolated prototypes with tests for legacy password verification and signed-photo URLs. Once those prototypes pass, add the first database migration files and start the auth/session layer. After that, implement the domain pages and APIs in milestone order from the high-level plan.

Every new API route must use explicit request and response models. Every new mutation route must use `POST`, `PATCH`, `PUT`, or `DELETE`, never `GET`. The legacy Internkort endpoints may preserve the old shape for compatibility, but they must delegate to the new mobile-card service. The current `/login` route already follows this pattern: `GET /login` renders the form and `POST /login` performs the state change.

## Concrete Steps

All commands below are run from `/Users/kluvin/dev/kvarteret/kvarteret-personal` unless stated otherwise.

Create the repository scaffolding:

    uv init --package .
    npm init -y
    npm install -D tailwindcss @tailwindcss/cli
    uv add fastapi "uvicorn[standard]" jinja2 pydantic-settings sqlalchemy alembic asyncpg httpx itsdangerous supabase python-multipart email-validator passlib pytest pytest-asyncio

Run the server once the scaffold exists:

    make run

Check the health endpoint:

    curl -i http://127.0.0.1:8000/health

Run tests:

    make test

Run the live auth smoke test once `SUPABASE_SECRET_KEY` and `DATABASE_URL` are set:

    make smoke-auth

Recover the old Azure-hosted image and document payloads:

    scripts/download_legacy_azure_media.sh all

Upload the recovered image archive into Supabase Storage:

    make upload-legacy-images

Or restrict the import to files referenced by `public.personal_bilde`:

    uv run python scripts/upload_legacy_images_to_supabase.py --db-backed-only

Create a direct auth-backed admin account for local testing:

    uv run python scripts/bootstrap_auth_user.py \
      --email <email> \
      --username <username> \
      --password 'choose-a-password' \
      --display-name '<display-name>' \
      --role admin

Apply the additive auth/session support tables to Supabase:

    Use the Supabase migration tool or repository migration SQL so that these public tables exist:
    `user_accounts`, `group_admin_memberships`, `web_sessions`, and `auth_migration_events`.

Apply the additive registration/mobile support tables and create the private buckets:

    Use the repository migration SQL so that these structures exist:
    `public.registrering`, `public.nytt_personal`, `public.personal.internkort_access_token_created_at`
    and the private Storage buckets `personnel-photos` and `personnel-documents`.

## Validation and Acceptance

The current slice is accepted when:

A novice can start the server locally and receive HTTP 200 from `/health`.

A novice can open the root page and be redirected to `/login`, then see the login form.

`uv run pytest` passes and includes tests for the legacy password verifier, the storage service, the new and legacy mobile API shapes, the bridge login service, people photo/document writes, registrations, semester transfer, the admin-only users slice, and the protected web routes.

`make smoke-auth` creates a temporary real auth user, logs in through `POST /login`, receives a signed web session, successfully loads `GET /api/v1/auth/me`, and removes the temporary auth and app records.

`scripts/download_legacy_azure_media.sh all` downloads the `images` blob container into `data/legacy-images/` and writes a `personal_fil` archive into `data/legacy-personal-fil/`. If the App Service `files` directory is empty, the script prints that explicitly.

## Idempotence and Recovery

The scaffold is additive and safe to rerun. Python and npm installs can be repeated without damaging the repository. Later database work must happen first on a Supabase development branch, not production. When migrations begin, already-applied migration files must remain immutable.

The legacy-media recovery script is also safe to rerun. The image path uses AzCopy with `--overwrite=ifSourceNewer`, and the App Service zip fetch simply refreshes `data/legacy-personal-fil/files.zip` plus its extracted directory.

## Artifacts and Notes

Initial evidence captured during research:

    aspnet_users = 66
    auth_users = 0
    personal.brukerkonto linked rows = 0

Evidence from the current implemented slice:

    Health response:
      HTTP/1.1 200 OK
      {"status":"ok"}

    Pytest summary:
      collected 47 items
      tests/test_auth_api.py .
      tests/test_groups_courses_api.py ...
      tests/test_groups_courses_web.py .
      tests/test_health.py ..
      tests/test_legacy_passwords.py ...
      tests/test_login_service.py ...
      tests/test_mobile_card_api.py ...
      tests/test_media.py ...
      tests/test_people_api.py ....
      tests/test_registrations_api.py ..
      tests/test_registrations_web.py .
      tests/test_people_web.py .
      tests/test_postgrest_services.py ...
      tests/test_search_api.py .
      tests/test_search_service.py ...
      tests/test_search_web.py .
      tests/test_session_store.py ..
      tests/test_storage.py ..
      tests/test_users_api.py ...
      tests/test_users_web.py ..
      tests/test_web_auth.py .
      40 passed in 1.59s

    Supabase table existence check:
      auth_migration_events
      group_admin_memberships
      user_accounts
      web_sessions

    Current document inventory:
      personal_fil rows = 88
      group-scoped rows = 85
      people with files = 47
      file types = 79 pdf, 9 jpg


    Live auth smoke:
      LOGIN_OK <temporary-test-email> admin 5

    Performance evidence:
      people.list with per-row Storage signing: 7127.6 ms
      people.list without per-row Storage signing: 160.2 ms
      people.list after backend media URLs, warm path: 160.9 ms
      session.load before cache: 212.8 ms
      session.load after cache, first hit: 215.5 ms
      session.load after cache, second hit: 0.0 ms
      groups.list on internal PostgREST, warm path: 276.8 ms
      courses.list on internal PostgREST, warm path: 110.8 ms

## Interfaces and Dependencies

Use FastAPI for the HTTP server, Jinja2 for HTML templates, HTMX for partial page updates, Tailwind for styling, SQLAlchemy with `asyncpg` for direct database work, and the official Supabase Python client for Auth and Storage integration.

At the end of the current scaffold slice, these interfaces should exist:

    app.config.Settings
    app.main.create_app() -> FastAPI
    app.auth.legacy_passwords.verify_aspnet_identity_hash(encoded_hash: str, password: str) -> bool
    app.services.storage.create_photo_signed_url(path: str, expires_in: int = 60) -> str
    app.auth.login_service.LoginService.login_with_bridge(...)
    app.auth.session_store.SessionStore.create_session(...)
    app.auth.repository.DatabaseAuthRepository

Revision note: This revision reflects the first auth milestone. It records the live Supabase auth/session tables, the protected-route behavior, the implemented rolling-bridge service layer, and the expanded passing test suite.

Revision note: This revision also records the addition of a top-level `Makefile` so common local workflows are accessible through `make`.

Revision note: This revision records the first real domain slice beyond auth: protected list/detail pages and English JSON APIs for people, groups, and courses, plus person-document metadata carried forward from `personal_fil`.

Revision note: This revision records the repaired session-pooler database URL, the live SQL smoke checks, the advanced search port, the first explicit auth identity API endpoint, the live auth smoke workflow, the new admin-only users slice, the backend media proxy change that removed per-row Storage signing from the people list, the new in-process session cache, and the first internal PostgREST-backed list reads.

Revision note: This revision records the additive registration/mobile migration applied to Supabase, the private Storage buckets, the real photo/document write paths, the registration invite/submit/approve flow, the real mobile-card OTP/session flow with the legacy adapter still in place, the semester-transfer workflow, the repaired live-auth cleanup script, and the expanded 47-test suite.

Revision note: This revision also adds `architecture.md` so a new contributor can orient themselves in the implemented system without reconstructing the current runtime shape from code alone.
