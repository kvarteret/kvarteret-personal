# Preserve public application choices while routing the primary placement

This ExecPlan is a living document and must be maintained in accordance with the repository-level `PLANS.md` guidance.

## Purpose / Big Picture

Applicants can select two distinct public options such as Halvtimen and Grøndahls even though both are operationally administered by Skjenkegruppen. After this change, Personal will show those submitted options exactly as application metadata, while only the primary option controls the suggested group and role used during promotion. The secondary option will not appear as an alternative promotion target.

## Progress

- [x] (2026-08-10 13:10Z) Traced the website payload, Personal intake routing, persistence, detail query, and promotion option builder.
- [x] (2026-08-10 13:25Z) Added persisted snapshot labels for the submitted first and second choices, including a safe migration/backfill.
- [x] (2026-08-10 13:28Z) Routed only the primary choice into the suggested operational group and role; retained the secondary choice only as display metadata.
- [x] (2026-08-10 13:32Z) Updated list/detail rendering and promotion options to use the submitted labels and exclude the secondary choice from actionable promotion choices.
- [x] (2026-08-10 13:40Z) Added focused unit, web, migration, and end-to-end coverage; all 290 non-Postgres tests pass and the Postgres suite collects but skips locally because `E2E_DATABASE_URL` is unavailable.

## Surprises & Discoveries

- Observation: Distinct bar-area slugs are deliberately mapped to the same `skjenke-gruppen` group ID, and only the first slug is mapped to a role. Consequently, the current two group-ID columns cannot preserve the submitted distinction.
  Evidence: `app/domain/volunteer_applications/service.py` maps all public bar options through `_PUBLIC_PROSPECT_ROLE_ROUTES` before persistence.
- Observation: The promotion selector deduplicates choices by group ID, so two bar-area selections collapse to one option even before rendering.
  Evidence: `_build_promotion_group_options` in `app/web/routes/volunteer_applications/pages.py` uses `seen_group_ids`.
- Observation: Existing affected records cannot recover the original second bar choice because only the shared parent group ID was persisted.
  Evidence: The migration can backfill the first label from `initial_role_id`, but the second label can only fall back to the saved group name.
- Observation: The repository's complete Alembic history is PostgreSQL-specific and cannot be executed from baseline on SQLite because an older migration creates the `pg_trgm` extension.
  Evidence: A local SQLite `alembic upgrade head` stopped at `20260313_1545_people_search_pg_trgm_support.py`; the new migration is instead exercised directly through Alembic Operations in a focused SQLite test and covered in the Postgres E2E path for CI.

## Decision Log

- Decision: Persist immutable first- and second-choice display labels alongside the existing operational group references.
  Rationale: The public slug is routing input, while the label is the human-facing application fact that must survive later group renames or many-to-one routing. This is additive and permits a safe backfill for existing records.
  Date/Author: 2026-08-10 / Codex
- Decision: Keep only the primary choice actionable during promotion.
  Rationale: The user clarified that the second choice is metadata. The primary routed group and role are the suggested final placement; the second choice is context for reviewers, not a selectable assignment.
  Date/Author: 2026-08-10 / Codex

## Outcomes & Retrospective

New applications now retain distinct submitted labels such as `Halvtimen / Grøndahls`, while Halvtimen alone determines the suggested `Skjenkegruppen / Halvtimen-skjenker` placement. The secondary choice is visible metadata and no longer appears in promotion options or allowed promotion group IDs. Existing affected records improve where the first role identifies the choice, but their original second bar choice remains unrecoverable from stored data.

## Context and Orientation

The public website posts `first_choice_group_slug` and an optional `second_choice_group_slug` to `POST /api/v1/volunteer-prospects`. In Personal, `app/domain/volunteer_applications/service.py` resolves those slugs. Public bar options such as `halvtimen` route to an operational parent group and role. `app/domain/volunteer_applications/repository.py` writes the registration to `volunteer_application_invites`; `queries.py` and the repository detail query read it for the admin pages. The detail template displays committee wishes and offers the promotion action.

An operational group is the Personal group that owns membership and roles. A submitted choice is the public-facing option selected by the applicant. They are not always the same entity: Halvtimen is a submitted choice but is implemented as a role under the operational Skjenkegruppen group.

## Plan of Work

Add nullable text columns for first- and second-choice labels to the SQLAlchemy table and an Alembic migration. Backfill existing labels from the joined group names, preferring the initial role name for the first choice where a routed role is already present. Extend repository creation, list, and detail reads to use the snapshot label when available and fall back to group names for compatibility.

Extend the public routing metadata so each bar option has a stable display label. Resolve the first choice into its operational group and optional suggested role. Resolve the second choice sufficiently to validate that it is configured, but store it only as metadata and do not make it an accepted promotion group. Preserve the existing external request contract.

Change the promotion option builder so only the initial/first operational placement is actionable. Add tests proving that Halvtimen plus Grøndahls displays as two distinct submitted choices, suggests Halvtimen-skjenker, and offers only the primary Skjenkegruppen placement during promotion.

## Concrete Steps

Work from the repository root. Before editing, run `git status --short` and preserve unrelated changes. Apply the migration and source edits, run the focused tests with `uv run pytest`, and then run the repository test command. Run Alembic against a disposable test database through the existing end-to-end harness when available.

## Validation and Acceptance

A service test submitting `halvtimen` first and `grondahls` second must persist the labels `Halvtimen` and `Grøndahls`, set the primary operational group to Skjenkegruppen, and set the suggested role to `Halvtimen-skjenker`. A page test must render `Halvtimen / Grøndahls`. A promotion-option test must expose one actionable Skjenkegruppen placement and must not add a second option from the metadata-only choice. Existing non-routed group submissions must continue to show their group names.

## Idempotence and Recovery

The migration is additive. Its upgrade may be rerun only through Alembic's normal revision tracking. Downgrade removes the two added columns; no existing group or registration records are deleted. Source changes retain fallback behavior for registrations created before the migration.

## Artifacts and Notes

The observed broken state is a detail page showing `Skjenkegruppen / Skjenkegruppen` with `Halvtimen-skjenker` as the selected role. This proves that the first public choice survived only indirectly through the suggested role and the second public choice was lost.

## Interfaces and Dependencies

No HTTP request or response model changes are required. `VolunteerApplicationsRepository.create_public_prospect_registration` will accept `first_choice_label: str` and `second_choice_label: str | None`. `VolunteerApplicationListItem` and `VolunteerApplicationDetail` will continue exposing `first_choice_group_name` and `second_choice_group_name` to templates, but query construction will populate those values from the immutable labels first and joined group names second. This keeps template compatibility while correcting the meaning shown to reviewers.

Revision note (2026-08-10): Initial plan created after confirming the many-to-one subgroup routing and the user's requirement that the secondary choice remain metadata only.

Revision note (2026-08-10): Marked implementation and verification complete, documented the historical-data limitation and PostgreSQL-only migration-suite constraint, and recorded the final test evidence.

Revision note (2026-08-14): Replaced the obsolete temporary-worktree instruction with repository-root guidance and pointed the plan at this repository's `PLANS.md`.
