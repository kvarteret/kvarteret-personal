# Current Documentation Issues

This is the running issue list for the documentation overhaul. Keep it current as discoveries are made.

## Fixed in This Overhaul

- The top-level README framed the repository as an in-progress one-time migration instead of the current service. It is being replaced with a current overview and links into `docs/`.
- The old architecture page mixed stale migration-era statements with current runtime facts. It is being replaced by a pointer to the canonical architecture explanation under `docs/explanation/`.
- API boundaries with `kvarteret-internbevis-rn`, `samfunnetibergen`, and `frontend-eventside` were not documented in one place. They are now canonical in `docs/reference/api-boundaries.md`.
- Third-party systems were scattered across code and old prose. They are now canonical in `docs/reference/external-systems.md`.

## Open Issues

### Event writes bypass `kvarteret-personal`

`frontend-eventside` writes event rows directly through Supabase. `kvarteret-personal` owns migrations and public read APIs, but it does not yet own event write endpoints.

Impact: validation, write authorization, image handling, and publication rules are split between frontend code, Supabase policies, and backend migrations.

Suggested follow-up: design backend event write APIs or explicitly document the intended long-term direct-Supabase contract.

### StudentBergen boundary is workflow-level, not implemented here

`frontend-eventside` contains StudentBergen API docs and workflow context, but `kvarteret-personal` does not currently call StudentBergen directly.

Impact: documentation can easily overstate this as a backend integration.

Suggested follow-up: document the actual StudentBergen publication flow in `frontend-eventside`, then link to it from the system map.

### Legacy personaldatabase repos are archive-safe

`Personaldatabase_Backend` and `Personaldatabase_Frontend` still have their own READMEs and operational instructions. The organization README should explain that `kvarteret-personal` is the current service boundary without deleting useful legacy repo descriptions.

Impact: new contributors may not know whether to use old or new repos.

Investigation result on 2026-05-05 before the final product decision:

- `api.kvarteret.no` still resolved to `personaldatabasen-api.azurewebsites.net` and responded from Kestrel. A test POST to `/api/DigitalInternkort/RequestAccessTokenOnEmail` returned a live old-backend error message for an unknown email.
- `Personaldatabase_Backend` still has active deployment wiring: `.github/workflows/build-push.yml` builds/pushes `dakit/personaldatabase-backend:latest` from `master` and calls the Azure restart webhook. GitHub reports the repo is not archived, default branch `master`, last pushed `2026-03-11T13:13:28Z`.
- `Personaldatabase_Frontend` had weaker live evidence. `intern.kvarteret.no` did not resolve during the check, and GitHub reports the repo is not archived, default branch `master`, last pushed `2026-02-20T16:33:34Z`. It still has deployment wiring for `dakit/personaldatabase-frontend:latest`, but no live DNS evidence was found for the old frontend.
- `frontend-eventside` still contained a helper that pointed to `https://api.kvarteret.no/api/DigitalInternkort`.

Product decision on 2026-05-05:

- The user confirmed the old backend has been replaced by new clients and should be treated as safe to archive.
- The organization README now labels both `Personaldatabase_Backend` and `Personaldatabase_Frontend` as replaced/archive-safe, with `kvarteret-personal` as the replacement.

Suggested follow-up:

- Archive `Personaldatabase_Backend` and `Personaldatabase_Frontend` in GitHub when ready to perform the external action.
- Repoint or retire `api.kvarteret.no` so it does not imply an active legacy backend.
- Remove or quarantine old `personaldatabase-backend` and `personaldatabase-frontend` profiles from `infra` after the archive action.

### Environment ownership is spread across Vercel, Supabase, and local `.env`

The code has a clear settings model, but deployed values live outside the repo.

Impact: incidents can be misdiagnosed from source alone.

Suggested follow-up: create an operations runbook for checking deployed Vercel env vars and Supabase dashboard settings when production behavior differs from local source.

### Organization profile README is separate from this repo

The requested organization README lives in `/Users/kluvin/dev/kvarteret/.github-private/profile/README.md`, not in `kvarteret-personal`.

Impact: documentation changes span two repositories and must be reviewed/committed separately.

Suggested follow-up: commit or PR the profile README separately from the `kvarteret-personal` docs.
