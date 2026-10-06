# Export volunteer counts to PostHog

`public.warehouse_volunteer_counts` is an aggregate-only export table. It counts
distinct volunteers with recorded role assignments, by semester and group, plus
an organisation total deduplicated across groups. This follows
`app/domain/groups/queries.py:get_org_stats_detailed`. It includes unsigned and
trial assignments and historical groups, regardless of their current active flag.
It is not the stricter current active-volunteer metric in
`app/domain/volunteers/search_sql.py:current_active_volunteers_subquery`.

No names, contact information, volunteer IDs, contract statuses, application
details, or tokens are exported. Group counts below five are NULL with
`is_suppressed = true`; organisation totals remain exact. Suppression reduces
disclosure but does not guarantee anonymity: overlapping memberships, exact
totals, and repeated refreshes can reveal small changes. Limit access accordingly.

## Deploy and connect

1. Apply migration `20261006_1200` through the normal Personal deployment.
2. Run `uv run python -m scripts.refresh_warehouse_volunteer_counts` using the
   backend database environment. Schedule it before each warehouse sync, for
   example hourly with a six-hour PostHog sync. This PR supplies the command,
   not a production scheduler; schedule failure makes the export stale.
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
transaction and serializes concurrent refreshers. Changes to assignments are
reflected on the next rebuild; PostHog then reflects them on its next successful
full refresh. The table holds recomputed semester statistics, not daily snapshots.
Semesters/groups with no recorded assignments have no row; the absence of a
current semester row means zero only after a successful fresh rebuild.

## Query the counts

Select `scope_key = 'organisation'` for the organisation total; never sum group
rows to derive that total. Use `group_id` for group breakdowns and exclude
`is_suppressed = true` from exact-count charts. NULL means withheld, not zero.
Semester codes use `YYYY1` for spring and `YYYY2` for autumn.

For example, `20262 / organisation / NULL / 120` means 120 distinct assigned
volunteers in autumn 2026. `20262 / group:7 / 7 / NULL` with suppression enabled
means fewer than five assigned volunteers in group 7. One volunteer assigned to
two groups contributes to both group counts but only once to the organisation.

The migration and command must be deployed and the connector configured before
counts appear in PostHog. No source grants, production schedule, or PostHog
configuration are changed by creating or merging this PR.
