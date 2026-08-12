# Replace group registrations with independent friend-invited applications

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `PLANS.md` in the repository root. It describes a staged database and application migration in `kvarteret-personal`. The public form in the sibling `samfunnetibergen` repository continues sending the existing `friend_emails` request field; no sibling-site contract change is required for the core migration.

## Purpose / Big Picture

People may still add up to two friends when registering as volunteers. Each friend receives an ordinary invitation explaining that the named applicant invited them to volunteer together at Samfunnet i Bergen. After creation, every application is processed independently: one friend can submit, enter a trial period, be approved, be rejected, or remain unanswered without blocking or changing anyone else.

The system keeps the useful fact that one application invited another, but it no longer models those people as a group. Administrators see every application as its own list item and see a small informational note and links between related applications. There is no bulk approval, no requirement that every friend submit before one person can be approved, no “remove from group” action, and no grouped presentation of recently approved volunteers.

Existing data must survive the change. Every old application-group membership is converted into a directional inviter-to-invitee record before the old group tables are removed. Deleted applications remain represented by email snapshots where the old schema still contains them. Existing application states, submissions, trial periods, promoted volunteer records, choice labels, and email-delivery history are not recreated or reset.

## Progress

- [x] (2026-08-12 13:28Z) Read `AGENTS.md`, `.agents/README.md`, `PLANS.md`, and the repository documentation-boundary skill.
- [x] (2026-08-12 13:28Z) Traced the current public intake, application-group schema, state-machine guards, bulk approval, admin rendering, durable email preparation, domain events, tests, and sibling proxy contract.
- [x] (2026-08-12 13:28Z) Recorded the agreed model and staged migration in this ExecPlan.
- [ ] Run the production-data preflight queries and record their counts in `Surprises & Discoveries` before executing the backfill; this remains a deployment-time gate because no approved production database access is configured in the workspace.
- [x] (2026-08-12 15:58Z) Milestone 1 implementation: add the pairwise relationship table, transactional backfill guards/count checks, indexes, snapshots, and downgrade path.
- [x] (2026-08-12 15:58Z) Milestone 2: switch creation, email preparation, queries, admin rendering, and lifecycle behavior to independent applications.
- [ ] Milestone 3: verify migrated production behavior during a compatibility period in which old tables remain read-only; local E2E coverage is updated, but production reconciliation and queued-delivery inspection require approved deployment access.
- [x] (2026-08-12 15:58Z) Milestone 4 implementation: add the guarded contract migration, normalize historical source labels, remove obsolete runtime code, update durable documentation, and add validation coverage.

## Surprises & Discoveries

- Observation: friend applicants already have separate rows in `volunteer_application_invites`; the complexity comes from a second application-group layer rather than from a shared application row.
  Evidence: `app/domain/volunteer_applications/repository.py:create_public_prospect_registration` inserts the submitter, creates `volunteer_application_groups`, then inserts one additional `volunteer_application_invites` row per friend.

- Observation: the event log already records the directional relationship for newly created friend invitations.
  Evidence: `app/domain/volunteer_applications/workflow.py:register_public_prospect` emits `application_invited` with `invited_by_registration_id` in the payload.

- Observation: the current schema does not enforce exactly one inviter per application group.
  Evidence: `volunteer_application_group_members` constrains `role` to `inviter` or `invitee` and makes `(group_id, invite_id)` unique, but has no partial unique constraint for one inviter per `group_id`.

- Observation: deletion can null `volunteer_application_group_members.invite_id` while retaining `applicant_email`.
  Evidence: the foreign key in `app/domain/volunteer_applications/tables.py` uses `ON DELETE SET NULL`. The migration must therefore support relationships whose live application ID is unavailable.

- Observation: durable friend email is prepared at dispatch time, not creation time, and currently looks up the inviter through the group tables.
  Evidence: `app/email_message_preparation.py:EmailMessagePreparer._load_friend_inviter` joins group membership to submissions. Old tables cannot be dropped until every queued delivery can resolve through the new relationship.

- Observation: `scripts/render_email_previews.py` currently omits the friend-invitation template even though the renderer and compiled template exist.
  Evidence: `build_previews()` renders application receipt, direct invitation, profile completion, admin onboarding, and mobile-card email only. Add the friend template so its new wording receives visual verification.

- Observation: no approved production database URL or deployment credential is available in this workspace.
  Consequence: production preflight/reconciliation counts and live queued-email inspection were not run, and no `.env` database value was used. The migrations contain descriptive guards and count checks so deployment fails closed until the approved path is used.

- Observation: the application metadata must match the post-contract schema because the runtime no longer imports the retired group tables.
  Consequence: schema-drift validation is expected to compare the new relationship table against the final schema after the contract migration, while historical group-table references remain only in migration files and explicitly superseded documentation.

- Observation: the legacy group-member primary key is reused as the relationship ID during backfill.
  Consequence: the additive migration declares the new ID as an auto-incrementing Postgres primary key and resets its sequence after explicit historical IDs are inserted.

- Observation: PostgreSQL rejected the first long-form relationship index names because identifiers are limited to 63 bytes.
  Consequence: the final schema uses the short, explicit names `ix_va_friend_invites_inviter_id` and `ix_va_friend_invites_invitee_id`; a disposable Postgres 17 upgrade caught and verified this before handoff.

## Decision Log

- Decision: represent “invited by a friend” as one directional record per invited application, not as a group entity and not as bulk application state.
  Rationale: one inviter with two friends produces two ordinary relationships. This directly answers who invited whom without allowing one applicant’s state to control another.
  Date/Author: 2026-08-12 / Codex and product discussion

- Decision: keep both a queryable relationship row and an immutable `application_invited` domain event.
  Rationale: administrators need efficient indexed queries and links, while the event log should preserve the historical fact that an invitation occurred. JSON event payloads alone have no foreign-key guarantees and are awkward for routine list/detail queries.
  Date/Author: 2026-08-12 / Codex and product discussion

- Decision: do not synthesize ordinary `application_invited` events for historical relationships during migration.
  Rationale: those events would appear to be actions that occurred during migration. The backfilled relationship row carries the original membership timestamp; migration execution belongs in deployment and schema audit logs. If implementation requires a domain event, it must be explicitly named `friend_relationship_migrated` and must contain both the original timestamp and migration timestamp.
  Date/Author: 2026-08-12 / Codex and product discussion

- Decision: preserve relationship snapshots even when application foreign keys become null.
  Rationale: the existing group schema intentionally retains member email after application deletion. The replacement must not throw away information that still exists.
  Date/Author: 2026-08-12 / Codex and product discussion

- Decision: treat old dropped membership as historical metadata only.
  Rationale: `dropped_at` and `dropped_by_user_account_id` may be worth preserving for audit, but there is no active friend-group membership after this change and no “drop from group” action.
  Date/Author: 2026-08-12 / Codex and product discussion

- Decision: keep the public `friend_emails` request field and its current maximum of two.
  Rationale: `/Users/kluvin/dev/kvarteret/samfunnetibergen/apps/web/src/app/api/volunteer-prospects/route.ts` already forwards this field to `POST /api/v1/volunteer-prospects`. Keeping the contract avoids an unnecessary coordinated frontend deployment while changing the backend meaning from “make a group” to “make independent friend invitations.”
  Date/Author: 2026-08-12 / Codex

- Decision: preserve each existing friend application’s current committee choices during migration and initially copy the inviter’s choices for new friend invitations, as today.
  Rationale: this plan removes lifecycle enforcement without silently changing or erasing applicant data. Allowing a friend to edit prefilled committee choices is desirable, but the current `/apply/{token}` page does not expose the Sanity-backed public choice model. That product and cross-repository form change is a separate follow-up rather than a hidden expansion of this migration.
  Date/Author: 2026-08-12 / Codex

- Decision: use an expand-migrate-contract rollout.
  Rationale: “expand” adds the new table without breaking old code, “migrate” backfills and switches readers and writers, and “contract” removes old schema only after verification. This protects queued email and Vercel deployments in which old and new function instances may overlap briefly.
  Date/Author: 2026-08-12 / Codex

- Decision: keep the additive and contract migrations as consecutive revisions in this implementation, with production execution still gated by the preflight and reconciliation checks.
  Rationale: the repository needs one complete Alembic head and final runtime metadata for CI/schema-drift verification; deployment operators can stop after the additive revision for a compatibility window before advancing to the contract revision.
  Date/Author: 2026-08-12 / Codex

## Outcomes & Retrospective

The local implementation now treats friend invitations as pairwise informational relationships and gives every application its own lifecycle. The focused suite passes (`139 passed`), the full fast suite passes (`318 passed`), and a disposable Postgres 17 database upgraded through Alembic head with schema drift clean; the real migrated E2E suite passes (`12 passed`). Email assets, E2E assertions, docs, and the OpenAPI artifact are updated. Production migration counts, compatibility duration, and live outbox inspection remain deployment-time evidence because no approved production database access was available here. No historical fields are intentionally discarded by the backfill; legacy dropped timestamps and email/name snapshots are preserved.

## Context and Orientation

`kvarteret-personal` is a FastAPI application with a server-rendered Jinja admin UI and a Supabase-hosted Postgres schema managed by Alembic. A “registration,” “application,” and `volunteer_application_invites` row refer to the same volunteer-application lifecycle. Domain code generally calls its primary key `registration_id`; web route parameters often call it `application_id`.

Public intake is owned by `app/api/v1/volunteer_prospects.py`. Its `PublicVolunteerProspectRequest` accepts the applicant, two committee-choice slugs, and optional `friend_emails`. `app/domain/volunteer_applications/service.py:create_public_prospect_registration_record` validates that neither the applicant nor friends already have active records and resolves public choice slugs. `app/domain/volunteer_applications/repository.py:create_public_prospect_registration` inserts the main application and submission, an application row for every friend, one group row, and group-member rows with inviter/invitee roles.

The sibling website `/Users/kluvin/dev/kvarteret/samfunnetibergen` owns the public React form. Its `apps/web/src/features/grupper/components/GroupVolunteerForm.tsx` collects at most two friend addresses. Its `apps/web/src/app/api/volunteer-prospects/route.ts` maps `friendEmails` to the API field `friend_emails`. The request and response shapes remain unchanged in this plan, so the sibling code needs regression testing but no functional edit.

The group schema is declared in `app/domain/volunteer_applications/tables.py` as `volunteer_application_groups` and `volunteer_application_group_members`. The latter stores a nullable application foreign key, a non-null email snapshot, inviter/invitee role, active/dropped status, creation time, and drop audit fields. The current Alembic head at plan creation is `20260811_1205`; new migrations must use the actual head at implementation time rather than hard-coding that value.

The state machine in `app/domain/volunteer_applications/state_machine.py` contains a membership state and a guard that rejects per-person promotion when `TransitionContext.is_part_of_active_group` is true. `app/domain/volunteer_applications/workflow.py:approve_group` promotes all members in one transaction. `app/domain/volunteer_applications/service.py` additionally blocks promotion until every active group member has submitted. These are the behavioral rules to remove; the ordinary individual state transitions remain.

Read behavior is split between `app/domain/volunteer_applications/queries.py` for lists and recent registrations and `app/domain/volunteer_applications/repository.py` for application detail. The models in `app/domain/volunteer_applications/models.py` currently expose `group_id`, `group_role`, `group_status`, `group_members`, and `renders_group`. Replace these with small friend-invitation summary types that do not carry lifecycle authority.

Admin routes are in `app/web/routes/volunteer_applications/pages.py` and `actions.py`. The grouped list is rendered by `app/templates/components/volunteer_applications/volunteer_applications_list.html`; the group detail panel and blocked promotion UI are in `app/templates/pages/volunteer_applications/volunteer_application_detail.html`; and recently approved volunteers are grouped in `app/templates/components/volunteer_applications/recent_volunteer_registrations.html`.

Volunteer email is durable. `app/domain/volunteer_applications/workflow.py` enqueues `APPLICANT_FRIEND_INVITATION`; `app/email_message_preparation.py` later loads current business data and renders it through `app/infrastructure/email/applicant_templates.py`. The source template is `app/templates/emails/mjml/applicant_friend_invitation.mjml`; `bun run build:emails` regenerates the compiled and preview artifacts. Because preparation happens later, the new relationship must be readable for deliveries queued before deployment.

`domain_events`, declared in `app/domain/volunteer_applications/tables.py`, is an append-only lifecycle audit table. An `application_invited` event is already emitted for each friend and contains `invited_by_registration_id`. The relationship table is the ordinary read model; the event is the audit record. A “read model” here means database data shaped for efficient display and lookup rather than for replaying historical events.

## Plan of Work

### Milestone 1: audit and add the pairwise relationship

Before editing schema, run read-only SQL against a recent production snapshot or production through the approved database access path. Count application groups, groups with no inviter, groups with more than one inviter, groups with no invitees, duplicate live invitees, null inviter IDs, null invitee IDs, dropped invitees, queued friend-email deliveries, and mixed application states. Record counts in `Surprises & Discoveries`. Do not guess how to map a zero- or multiple-inviter group. Stop the backfill and resolve those specific rows explicitly.

Add `volunteer_application_friend_invitations` to `app/domain/volunteer_applications/tables.py` with these fields:

    id                              BigInteger primary key
    inviter_application_id          nullable BigInteger foreign key to volunteer_application_invites.id, ON DELETE SET NULL
    invitee_application_id          nullable BigInteger foreign key to volunteer_application_invites.id, ON DELETE SET NULL
    inviter_name_snapshot           nullable Text
    inviter_email_snapshot          non-null Text
    invitee_email_snapshot          non-null Text
    created_at                      non-null timezone-aware DateTime
    legacy_dropped_at               nullable timezone-aware DateTime
    legacy_dropped_by_user_account_id nullable BigInteger foreign key to user_accounts.id

Index `inviter_application_id` and `invitee_application_id`. Add a unique constraint on non-null `invitee_application_id`; Postgres permits multiple nulls, which is required for already-deleted historical invitees. The `legacy_*` fields are read-only audit preservation and must not drive application behavior. Use the actual table and foreign-key naming conventions already present in the repository.

Create an additive Alembic migration under `migrations/versions/`. In one transaction, create the table and backfill one row for every legacy invitee membership. Resolve the inviter from the membership with `role='inviter'`. Use membership email snapshots even when application IDs are null. Resolve `inviter_name_snapshot` from `volunteer_application_submissions` when the inviter application still exists; leave it null when the name is genuinely unavailable rather than inventing a name. Use the invitee membership’s `created_at`, `dropped_at`, and `dropped_by_user_account_id`.

Make the migration fail with a descriptive exception if a legacy group has anything other than exactly one inviter. Validate row counts inside the migration: the new-row count attributable to backfill must equal the number of legacy `role='invitee'` rows. The downgrade removes only the new table and indexes; it must not modify the old group data.

Expose the new table through `app/db/tables.py` and schema-drift metadata. Add migration tests or E2E assertions covering active, dropped, deleted-inviter, deleted-invitee, and mixed-state groups. At the end of this milestone, old application behavior is unchanged, but every historical friend relationship has a safe pairwise representation.

### Milestone 2: write and read independent applications

Change `VolunteerApplicationsRepository.create_public_prospect_registration` so it no longer inserts an application-group row or group memberships. It still creates one ordinary application row per friend in the same transaction as the inviter, preserving the current duplicate checks, copied committee-choice snapshots, personal token, and durable email intent. For each friend, insert one `volunteer_application_friend_invitations` row pointing from the submitter’s application to that friend’s application, with inviter name/email and invitee email snapshots. Use a transitional source policy: new rows may use `source='friend_invite'`, but every reader and template must continue recognizing historical `source='group_invite'` until Milestone 4.

Keep the existing `application_invited` event and enrich new event payloads with non-secret snapshots needed for durable history: `invited_by_registration_id`, `inviter_name`, `inviter_email`, and `invitee_email`. Do not place invitation tokens in event payloads. Continue making the event and email-outbox insertion part of the registration transaction.

Replace `VolunteerApplicationGroupMember` with a plain friend-invitation summary model in `app/domain/volunteer_applications/models.py`. Application list and detail models should expose an optional `invited_by` summary and a list of `friend_invitees`. Each summary may carry surviving application ID, display name/email snapshot, created time, and legacy drop metadata. It must not expose an “active group” property or participate in transition guards.

Update list and detail queries to join or batch-load the new table. Every application row must appear once in the admin list, including inviter and invitees. On an invitee detail page, show “Invitert av <name or email> til å søke sammen” and link the inviter application when its ID survives. On an inviter detail page, show “Inviterte <names or emails> til å søke sammen” and link surviving invitee applications. A legacy dropped relationship may be labeled as historical, but there is no button to change it.

Remove `MembershipState`, `ApplicationAction.DROP_MEMBER`, `membership_transition`, `TransitionContext.is_part_of_active_group`, the group-approval exception, and all group-specific workflow/service/repository protocols. Remove `approve_group`, `approve_volunteer_application_group`, `_ensure_group_members_ready_for_promotion`, `drop_group_invitee`, and their side effect. The ordinary `/volunteer-applications/{application_id}/approval` path becomes available based only on that application’s own state and required submission data.

Remove the POST routes `/volunteer-applications/groups/{group_id}/approval` and `/volunteer-applications/{application_id}/drop-from-group` from `app/web/routes/volunteer_applications/actions.py`. Remove the grouped card, bulk approval button, blocked individual approval message, and drop form from the Jinja templates. Change recent-registration queries and rendering so promoted volunteers always appear individually; a friend note may remain on the application detail, but it must not group volunteer records.

Update `app/email_message_preparation.py` so friend-email preparation loads the inviter snapshot from `volunteer_application_friend_invitations` by invitee application ID. This must work for both already-queued `applicant_friend_invitation` rows and new deliveries. If the inviter application has been deleted, use the stored name when present and otherwise the inviter email snapshot; do not fail an otherwise deliverable friend email merely because the original application no longer exists.

Change the friend email subject and Norwegian lead text to the agreed message:

    <name> har invitert deg til å bli frivillig sammen på Samfunnet i Bergen!

The body must state that the recipient sends an individual application, applications are processed separately, the wish to begin together is retained as a note, and participation is not binding. Keep an English equivalent if the current bilingual template remains the product standard. Preserve the personal `/apply/{token}` link. Update `ApplicantEmailTemplateRenderer` parameters if the committee name is no longer needed in the copy.

Add the friend invitation to `scripts/render_email_previews.py`, compile the MJML, and inspect the generated preview. Update Norwegian gettext strings where the public token page currently says the friend is part of a group. Do not redesign committee-choice editing in this milestone; preserve current choice data and document the follow-up in `Outcomes & Retrospective`.

### Milestone 3: compatibility verification before schema removal

Deploy the additive migration before or with code that is capable of reading both old and new source labels. Keep `volunteer_application_groups` and `volunteer_application_group_members` present but stop all writes to them. During the compatibility period, run read-only reconciliation queries proving that every legacy invitee membership has exactly one new relationship and that every new `friend_invite` application has exactly one relationship.

Exercise at least these production-like scenarios: a new solo application; an inviter with one friend; an inviter with two friends; one friend submitting before the others; one friend entering trial and being approved while another remains new; one friend being rejected without changing the others; resending a friend invitation queued before the code switch; deleting an unanswered friend application while retaining relationship snapshots; and viewing already-promoted members from an old group as separate recent registrations.

Inspect durable email deliveries and confirm that no `applicant_friend_invitation` fails with `inviter_record_missing`. Confirm that admin list counts equal application-row counts after status filtering, rather than group-card counts. Record reconciliation counts and the duration of the compatibility period in this plan. Do not proceed to Milestone 4 while unmatched relationships or queued-email preparation failures remain.

### Milestone 4: contract the schema and documentation

Create a later Alembic migration, based on the then-current head, which first repeats the reconciliation guard. Update historical `volunteer_application_invites.source='group_invite'` rows to `friend_invite` only after all deployed code recognizes both values. Then drop `volunteer_application_group_members` and `volunteer_application_groups`. The downgrade may recreate empty legacy tables for structural reversibility, but it cannot truthfully reconstruct groups after new independent invitations have been created; document that limitation in the migration docstring and use database backup/restore as the data rollback strategy.

Remove transitional source handling and obsolete imports, models, repository methods, test fakes, and group-specific terminology. Search the repository for `volunteer_application_groups`, `volunteer_application_group_members`, `group_invite`, `approve_group`, `drop-from-group`, `group_role`, `group_status`, `group_members`, `renders_group`, and the Norwegian `Grupperegistrering`; remaining matches must be migrations, schema snapshots, or explicit historical explanation.

Update `docs/reference/api-boundaries.md` to say that `friend_emails` creates independent application invitations with informational pairwise links and individual approval. Update `docs/how-to/run-tests.md` so its E2E description no longer promises atomic group approval. Update any ADR or architecture explanation that describes membership state or bulk group promotion. Because the FastAPI request and response models remain unchanged, regenerate `openapi.json` and expect no semantic contract diff; still run the contract check to prove this.

## Concrete Steps

Work from `/Users/kluvin/dev/kvarteret/kvarteret-personal`. Before each milestone, preserve unrelated user changes:

    git status --short

For the preflight, use a read-only transaction and adapt schema qualification to the approved database environment. The essential checks are:

    SELECT count(*) FROM public.volunteer_application_groups;

    SELECT group_id, count(*)
    FROM public.volunteer_application_group_members
    WHERE role = 'inviter'
    GROUP BY group_id
    HAVING count(*) <> 1;

    SELECT count(*)
    FROM public.volunteer_application_group_members
    WHERE role = 'invitee' AND invite_id IS NULL;

    SELECT status, count(*)
    FROM public.volunteer_application_group_members
    GROUP BY status;

Also join group memberships to `volunteer_application_invites` to count application states and query `email_deliveries` for unresolved `template_key='applicant_friend_invitation'` rows. Save only aggregate counts in this plan; do not paste names, emails, tokens, or other personal data.

Create migrations with Alembic using the actual current head:

    uv run alembic heads
    uv run alembic revision -m "add friend invitation relationships"

After implementing each migration against a disposable Postgres 17 database with the Supabase compatibility stubs from `.github/workflows/ci.yml`, run:

    DATABASE_URL=$E2E_URL uv run alembic upgrade head
    DATABASE_URL=$E2E_URL uv run python scripts/check_schema_drift.py

For the additive migration, also downgrade one revision and upgrade again, confirming legacy rows remain unchanged and the backfill is repeatable through downgrade/re-upgrade on the disposable database.

During application work, run focused tests after each coherent edit:

    DATABASE_URL=sqlite+aiosqlite:////tmp/kv-friend-applications.db uv run pytest -q \
      tests/unit/domain/test_state_machine.py \
      tests/unit/domain/test_volunteer_application_workflow.py \
      tests/unit/domain/test_data_services.py \
      tests/web/volunteer_applications/test_registrations_web.py

Compile and render email assets with:

    bun run build:emails

Open `app/templates/emails/previews/applicant_friend_invitation.html` locally and verify the inviter name, Samfunnet i Bergen wording, individual-processing explanation, button, and direct link at narrow and wide widths.

Run the fast repository suite and static gates:

    DATABASE_URL=sqlite+aiosqlite:////tmp/kv.db uv run pytest -q --ignore=tests/e2e
    uv run ruff check .
    uv run lint-imports
    DATABASE_URL=sqlite+aiosqlite:////tmp/kv-oas.db uv run python scripts/export_openapi.py --check
    bun run build:assets

Run the migrated Postgres E2E suite as documented in `docs/how-to/run-tests.md`:

    DATABASE_URL=$E2E_URL uv run alembic upgrade head
    E2E_DATABASE_URL=$E2E_URL DATABASE_URL=$E2E_URL uv run pytest tests/e2e -q

In `/Users/kluvin/dev/kvarteret/samfunnetibergen`, run the focused proxy and form-schema tests:

    npm --workspace @samfunnet/web run test -- \
      src/app/api/volunteer-prospects/route.test.ts \
      src/features/grupper/domain/volunteerFormSchema.test.ts

These tests must continue proving that zero, one, and two friend emails are forwarded correctly.

## Validation and Acceptance

The change is accepted when a public applicant can add one or two friend emails and receives the same successful `201` API response as before. Each person has a distinct `volunteer_application_invites.id` and personal token. The database contains one `volunteer_application_friend_invitations` row per friend and contains no new application-group memberships.

The friend receives an email whose lead says that the named inviter invited them to volunteer together at Samfunnet i Bergen. The email links to the friend’s own `/apply/{token}` page, explains that applications are individual, and does not promise joint approval or guaranteed shared shifts.

The admin application list displays inviter and friends as separate entries. Their detail pages show informational inviter/invitee notes and links. Starting trial, approving, rejecting, reopening, restoring, resending, or deleting one application affects only that application. Direct POST access to the former group-approval and drop-from-group routes returns 404 after removal.

An inviter can be approved while a friend has not submitted, and a friend can be approved while the inviter or another friend remains in a different state. The ordinary state machine still rejects promotion without submitted details and still enforces all non-group lifecycle rules.

Migrated historical groups retain the same application status, submission, choice labels, trial timestamps, promoted volunteer IDs, and role assignments. Each old invitee has one directional friend relationship. If either application was previously deleted, its surviving email snapshot remains visible as historical context without a broken required foreign key. No migration creates a false ordinary invitation event at migration time.

Queued friend email created before the switch can still be prepared and sent after the switch. The email outbox contains no new `inviter_record_missing` failures caused by table removal. Recent approved volunteers render individually.

All focused tests, the fast suite, Postgres E2E suite, schema drift check, Ruff, import contracts, OpenAPI check, and asset build pass. `rg` finds no runtime dependency on the removed group tables or behavior.

## Idempotence and Recovery

The preflight is read-only and may be repeated. The additive migration is transactional and retains old tables, so an application deployment can be rolled back without losing the new relationship rows. If backfill encounters malformed groups, the transaction must abort before creating a partial schema state; correct or explicitly map the anomalous rows, record the decision here without personal data, and rerun.

Do not run the contract migration until reconciliation succeeds and all queued friend deliveries can prepare through the new table. Before dropping old tables in production, take the normal managed Postgres backup and record its restore point. After the contract migration, application code can be rolled back only to a version that does not require old group tables. A full rollback to bulk-group behavior requires restoring the database backup because new independent invitations cannot be grouped truthfully after the fact.

Generated email HTML and previews may be rebuilt repeatedly with `bun run build:emails`. Disposable test databases may be destroyed and recreated. Never use production emails or tokens in fixtures, plan evidence, logs, or screenshots.

## Artifacts and Notes

The intended relationship for an inviter with two friends is:

    application 101 (Inga)
      -> friend invitation -> application 102 (Frida)
      -> friend invitation -> application 103 (Ola)

Applications 101, 102, and 103 each retain their own status and promotion path. The arrows provide context only.

A migrated deleted invitee remains representable as:

    inviter_application_id = 101
    invitee_application_id = NULL
    inviter_name_snapshot = "Inga Inviter"
    inviter_email_snapshot = "inga@example.test"
    invitee_email_snapshot = "deleted-friend@example.test"

Use synthetic addresses such as these in documentation and tests. Do not copy production rows.

## Interfaces and Dependencies

Define a relationship model in `app/domain/volunteer_applications/models.py`, with exact naming adjusted to repository conventions:

    @dataclass(frozen=True, slots=True)
    class VolunteerApplicationFriendRelationship:
        relationship_id: int
        inviter_application_id: int | None
        invitee_application_id: int | None
        inviter_name: str | None
        inviter_email: str
        invitee_email: str
        created_at: datetime
        legacy_dropped_at: datetime | None = None

Repository operations must include creation in the public-registration transaction and lookup by either side:

    async def create_friend_invitation_relationship(...) -> int
    async def get_friend_inviter(invitee_application_id: int) -> VolunteerApplicationFriendRelationship | None
    async def list_friend_invitees(inviter_application_id: int) -> list[VolunteerApplicationFriendRelationship]

The implementation may inline creation into `create_public_prospect_registration` to preserve its single transaction, but query methods must remain explicit and testable. Do not introduce a generic graph, generic relationship type, group aggregate, or new external dependency.

`EmailMessagePreparer` must resolve `APPLICANT_FRIEND_INVITATION` by invitee application ID through the new relationship. `ApplicantEmailTemplateRendererProtocol.render_friend_invitation_email` must accept only the values used by the revised template. The public API continues accepting `friend_emails: list[str] | None` and returning `registrationId`; its OpenAPI operation ID remains `createPublicVolunteerProspect`.

Revision note (2026-08-12): Created this ExecPlan from the product discussion and verified current source. Implementation completed locally with pairwise persisted relationships, domain-event audit, independent lifecycles, informational admin notes, guarded expand/contract migrations, updated generated assets, and green SQLite/Postgres validation. Production preflight and live outbox reconciliation remain deployment gates because no approved production access was available in the workspace.
