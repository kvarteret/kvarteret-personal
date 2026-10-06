# Plan individual admin accounts

Use the trial planner to connect existing admin accounts to volunteer profiles
before applying an account migration. It produces a private review artifact and
does not connect to a database or change accounts.

Individual accounts can be linked through `user_accounts.volunteer_id`.
Legacy accounts are marked with `is_legacy_account`. The
`LEGACY_ADMIN_LOGIN_ENABLED` setting defaults to `true`, preserving existing
logins during transition. When set to `false`, legacy accounts cannot establish
new web sessions or use existing ones, including impersonation sessions whose
originating account is legacy. This requires running the PR's application code;
older deployed code continues to accept existing logins.

Store the inventory, decisions, and output **outside every Git checkout**.
Never commit production names, emails, profile details, or mapping files.
The planner rejects paths inside checkouts, creates output with owner-only
permissions, refuses existing output files, and prints counts only.

Run from the Personal checkout:

```sh
uv run python scripts/plan_admin_volunteer_migration.py \
  --inventory /private/tmp/admin-volunteer-inventory.json \
  --decisions /private/tmp/admin-volunteer-decisions.json \
  --administration-group-id 263 --hovedstyret-group-id 2 --semester 20262 \
  --output /private/tmp/admin-volunteer-plan.json
```

The private inventory is a JSON object containing these arrays:

| Array | Required fields |
|---|---|
| `accounts` | `id`, `auth_user_id`, `role`; optional `display_name` |
| `volunteers` | `id`, `first_name`, `last_name`, `email` |
| `groups` | `id` |
| `memberships` | `auth_user_id`, `group_id` |
| `assignments` | `volunteer_id`, `semester`, `group_id` for administration membership |

The private decisions object is keyed by source account ID. Each entry accepts
an `action` of `map`, `remove`, `no_recipient`, or `pending`. A `map` decision
requires a nonempty `volunteer_ids` array. Optional `role` and `group_ids` fields
override existing access. A shared account can select several volunteers.
Set `reviewed` to `false` on a `map` entry to carry an unconfirmed private
proposal into the plan; its grants remain flagged for review.

Without an explicit selection, only unique exact-name matches with recorded
volunteer activity become proposals; they remain pending review. Organizational
placeholders and duplicate names stay unresolved. Shared or historical email
addresses alone do not establish identity. Use position history to review and
select holders in the private decisions file.

The output preserves every source account and records each person's source
grants. Several accounts for one volunteer produce one individual proposal,
with the highest access role and combined group scope. Missing personal emails,
shared personal emails, absent group scope, and unreviewed grants are flagged.
Removal decisions and accounts with no recipient generate no individual grant.

Supply both `--administration-group-id` and `--semester` to give everyone with
an assignment in Administrasjonen for that semester a full Admin proposal,
including people without an existing admin account. Historical assignments do
not qualify. This organizational grant is separate from source-account migration:
removing a legacy account does not remove a current member's eligibility.
The administration grant takes precedence over a source account's lower role.
`--hovedstyret-group-id` applies the same Admin eligibility rule to current
Hovedstyret members. Either group rule can run independently, with an explicit
semester. A member of both groups still produces one individual account, with
separate evidence for both organizational grants.

Review identity, preferred email, duplicate profiles, combined access, and
removal decisions before implementing a production migration. This trial has no
apply mode, authentication changes, invitations, or mobile permission changes.
