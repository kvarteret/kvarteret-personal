# Kvarteret Personal Architecture

This document describes the current architecture of the FastAPI rewrite in `/Users/kluvin/dev/kvarteret/kvarteret-personal`. It is written for someone who has only this repository and the live Supabase project.

## Purpose

The system replaces the old Angular frontend and ASP.NET backend with a server-rendered FastAPI application. It keeps the legacy personnel data model in Supabase Postgres, uses Supabase Auth for migrated web users, uses Supabase Storage for private photos and documents, and keeps the Digital Internkort app working through both a new English API and a temporary legacy adapter.

## High-Level Structure

The application is divided into five main areas.

- `app/main.py` creates the FastAPI app, mounts static assets, and installs the session-loading middleware.
- `app/web/` contains HTML routes that render Jinja templates for the admin interface.
- `app/api/` contains JSON routes. `app/api/v1/` is the new English API. `app/api/legacy/` contains temporary compatibility routes.
- `app/auth/` contains the web session model, the ASP.NET Identity bridge, Supabase Auth integration, and role handling.
- `app/services/` contains domain logic for people, groups, courses, search, users, registrations, semester transfer, mobile card, and storage.

The code intentionally keeps route handlers thin. Route handlers validate inputs, enforce authentication or admin access, and call services. Services do the database and storage work.

## Request Flow

An incoming browser request hits FastAPI in `app/main.py`. The middleware reads the signed session cookie, unsigns it, and loads the authenticated user through `app/auth/session_store.py`. The session store uses a short in-process cache to avoid a database hit on every request in the same worker.

After that, the request goes to either:

- an HTML route in `app/web/router.py`, which renders a template in `app/templates/`, or
- a JSON route in `app/api/router.py`, which dispatches to the v1 or legacy routers.

Protected routes use `require_authenticated_user()` from `app/auth/dependencies.py`. Admin-only routes currently use explicit admin checks in the route modules.

## Data Access

The system uses two data access strategies.

- SQLAlchemy Core is the default for direct database work. Shared table metadata lives in `app/db/tables.py`, and sessions come from `app/db/session.py`.
- PostgREST is used internally only for simple list reads where it reduces boilerplate. The internal client lives in `app/postgrest.py`.

There is no inline SQL in the repository code. The SQLAlchemy Core layer is used for auth, people detail, search, registrations, semester transfer, and the mobile-card flow. PostgREST is currently used for simple group and course list endpoints.

## Authentication and Authorization

Web authentication is session-cookie based.

1. `POST /login` calls `LoginService.login_with_bridge()` in `app/auth/login_service.py`.
2. If a migrated `public.user_accounts` row exists, the code signs in through Supabase Auth.
3. If no migrated account exists, the code checks the legacy ASP.NET Identity hash from `public.aspnetusers`.
4. On successful legacy login, the code creates the Supabase Auth user, upserts `public.user_accounts`, copies group-admin memberships, records an auth migration event, and creates a web session.
5. The browser stores only a signed opaque session id. The real session row lives in `public.web_sessions`.

The current role model is stored in `public.user_accounts.role` and represented in Python by `UserRole` in `app/auth/roles.py`.

## Storage and Media

Supabase Storage is private by default.

- `personnel-photos` stores profile photos by `{sha1}.{filetype}`.
- `personnel-documents` stores person documents by `{person_id}/{filename}`.

The backend does not embed Supabase signed URLs in list pages anymore. Instead, it generates short-lived application-signed media URLs through `app/media_tokens.py`, and the actual bytes are served by backend proxy routes in `app/api/media.py`.

This reduced the people-list latency dramatically because the server no longer signs one Supabase URL per row during HTML generation.

## Domain Areas

### People

`app/services/people.py` handles:

- people list and detail reads
- card, next-of-kin, and document metadata reads
- photo upload and delete
- document upload and delete

The person detail page in `app/templates/pages/person_detail.html` is the current operational hub for photos and documents.

### Groups and Semester Transfer

`app/services/groups.py` handles group list and detail reads. `app/services/semester_transfer.py` handles previewing and applying semester transfer for one group.

The web workflow is:

- `GET /groups/{id}` for group detail
- `GET /groups/{id}/semester-transfer` for preview
- `POST /groups/{id}/semester-transfer` to insert the next semester rows

The JSON API mirrors this under `/api/v1/groups/{id}/semester-transfer`.

### Courses

`app/services/courses.py` handles course list and detail reads, including required groups and recent completions.

### Search

`app/services/search.py` ports the legacy set-based search logic. It performs include and exclude filtering across groups and courses, birth-date windows, pingvin-point ranges, and current-semester variants.

### Users

`app/services/users.py` reads `public.user_accounts` and `public.group_admin_memberships`. These pages let admins inspect migrated and direct users.

### Registrations

`app/services/registrations.py` implements the new registration flow using the legacy-style tables:

- `public.registrering` stores invitation tokens and emails
- `public.nytt_personal` stores the submitted pending profile

The public flow is `/register/{token}`. The admin flow is `/registrations`.

### Mobile Card

`app/services/mobile_card.py` implements the Digital Internkort flow.

- `POST /api/v1/mobile-card/access-codes` generates and stores a six-digit code on `public.personal`.
- `POST /api/v1/mobile-card/sessions` verifies email plus code and returns a signed mobile session token and the current card payload.
- `GET /api/v1/mobile-card/me` rebuilds the live card from the signed session token.

The legacy endpoints under `/api/DigitalInternkort` call the same service and translate the response shape.

## Database and Supabase State

The hosted Supabase project already contained the copied legacy personnel schema. This repository has added only additive support tables and columns so far.

Implemented additive structures:

- `public.user_accounts`
- `public.group_admin_memberships`
- `public.web_sessions`
- `public.auth_migration_events`
- `public.registrering`
- `public.nytt_personal`
- `public.personal.internkort_access_token_created_at`
- storage buckets `personnel-photos` and `personnel-documents`

The repository still does not contain a full immutable baseline migration for the copied legacy public schema. That remains an operational gap.

## Performance Notes

Two important performance fixes have already landed.

- The app no longer signs Supabase URLs per person row. Media is served through backend proxy routes instead.
- Session resolution uses a short-lived in-process cache instead of hitting Postgres on every protected request.

The current deliberate split is:

- SQLAlchemy Core for complex and transactional flows
- internal PostgREST for simple list reads
- backend media proxy for private files

## Current Known Gaps

The system is operational for the implemented slices, but it is not fully finished.

- Group-admin scoped authorization is not fully implemented yet. Most admin mutations currently require full admin access.
- RLS policies are not yet enforced for the app tables.
- CSRF protection for browser mutations is not yet implemented.
- Full CRUD parity is still incomplete for some domains, especially broader create/update/delete coverage for groups, courses, and users.
- A full baseline migration for the copied legacy public schema is still missing.

## Operational Commands

Common commands are defined in `Makefile`.

- `make run` starts the app.
- `make test` runs the test suite.
- `make smoke-auth` performs a real create-login-cleanup smoke test against Supabase Auth.

## Source Map

Useful entry points:

- `app/main.py`
- `app/api/router.py`
- `app/web/router.py`
- `app/auth/login_service.py`
- `app/auth/repository.py`
- `app/services/people.py`
- `app/services/registrations.py`
- `app/services/mobile_card.py`
- `app/services/semester_transfer.py`
- `app/db/tables.py`
- `plans/fastapi-rewrite.md`
