# Export volunteer counts to PostHog

`public.warehouse_volunteer_counts` is an aggregate-only export table with two
explicit metrics. `metric = 'assigned'` counts
distinct volunteers with recorded role assignments, by semester and group, plus
an organisation total deduplicated across groups. This follows
`app/domain/groups/queries.py:get_org_stats_detailed`. It includes unsigned and
trial assignments and historical groups, regardless of their current active flag.

`metric = 'active'` provides the current-semester organisation headcount using
`app/domain/volunteers/search_sql.py:current_active_volunteers_subquery` and the
same volunteer-record join as Personal's `count_volunteers(only_active=True)`.
It includes current-semester signed assignments or assignments qualifying through
an unexpired trial, excludes assigned volunteers linked to `not_volunteer`
applications, and also includes linked unexpired trial volunteers without an
assignment. Membership is deduplicated by the shared builder. Active rows always
exist, including a zero count, and only cover the semester at refresh time.
Historical active counts and group attribution for trials without assignments
are not reconstructed. The `assigned` metric remains available for history.

No names, contact information, volunteer IDs, contract statuses, application
details, or tokens are exported. Group counts below five are NULL with
`is_suppressed = true`; organisation totals remain exact. Suppression reduces
disclosure but does not guarantee anonymity: overlapping memberships, exact
totals, and repeated refreshes can reveal small changes. Limit access accordingly.

## Deploy and connect

1. Apply migration `20261006_1200` through the normal Personal deployment.
2. Run `uv run python -m scripts.refresh_warehouse_volunteer_counts` using the
   backend database environment for an initial refresh. `vercel.json` schedules
   `/internal/cron/refresh-warehouse-volunteer-counts` hourly at minute 17 (UTC).
   The endpoint uses the existing `CRON_SECRET` bearer authentication and is
   excluded from public OpenAPI. Schedule failure makes the export stale.
3. Give a dedicated warehouse reader schema USAGE and SELECT on this export
   only. The table has RLS enabled and no public policies; `anon` and
   `authenticated` have no table grants. A dedicated non-owner reader needs a
   role-specific SELECT policy. Do not use the application's owner credential
   or grant access to `role_assignments` or `volunteer_records`.
4. Refresh source discovery in PostHog project 202551 and enable only
   `public.warehouse_volunteer_counts` for this metric. Use full refresh every
   six hours. Incremental/append-only modes can retain rows removed by a rebuild.
   The configured source prefix affects the SQL name: use the discovered name,
   not an assumed `supabase` or `personal` identifier.
5. Check the first completed sync, row counts and `refreshed_at`. Test source
   deletions and an empty-table refresh before relying on erasure propagation.

The migration creates an empty table. The command rebuilds it atomically in one
transaction and serializes concurrent refreshers. Assignment/application changes
and trial expiry are
reflected on the next rebuild; PostHog then reflects them on its next successful
full refresh. The table holds recomputed semester statistics, not daily snapshots.
Semesters/groups with no recorded assignments have no row; the absence of a
current assigned-semester row means zero only after a successful fresh rebuild.
The active organisation row explicitly reports zero when no volunteers qualify.

## Query the counts

Select `metric = 'active' AND scope_key = 'organisation'` for current active
headcount. Select `metric = 'assigned'` for assignment history and its group
breakdowns. Always filter the metric before aggregating to avoid combining two
different populations. Select `scope_key = 'organisation'` for the organisation total; never sum group
rows to derive that total. Use `group_id` for group breakdowns and exclude
`is_suppressed = true` from exact-count charts. NULL means withheld, not zero.
Semester codes use `YYYY1` for spring and `YYYY2` for autumn.

For example, `assigned / 20262 / organisation / NULL / 120` means 120 distinct assigned
volunteers in autumn 2026. `assigned / 20262 / group:7 / 7 / NULL` with suppression enabled
means fewer than five assigned volunteers in group 7. One volunteer assigned to
two groups contributes to both group counts but only once to the organisation.

The migration and command must be deployed and the connector configured before
counts appear in PostHog. Merging/deploying this PR installs the Vercel refresh
schedule; it does not grant a PostHog reader access or enable the connector sync.
