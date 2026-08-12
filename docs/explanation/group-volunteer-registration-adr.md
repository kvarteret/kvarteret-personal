# ADR: Group Volunteer Registration

Status: Superseded on 2026-08-12.

This document is retained as historical context for the retired grouped
registration model. The current model uses independent applications linked by
`volunteer_application_friend_invitations`; see [The Volunteer Application
Lifecycle](volunteer-application-lifecycle.md).

## Context

`samfunnetibergen` owns the public recruitment form and submits volunteer prospects to `kvarteret-personal`. The first grouped-registration version supports one inviter and up to two invited friends.

Friends inherit the inviter's group choices. They receive their own application link, complete their own profile details, and are reviewed in the same admin volunteer-application workflow as the inviter.

The feature needed to support group signup without losing audit history. In particular, removing an invitee from a group should not delete the original registration row or hide the fact that the person was once part of a grouped signup.

## Decision

Group volunteer signup is modeled with explicit group-registration tables:

- `registrering_gruppe` stores the linked signup event.
- `registrering_gruppe_medlem` links each `registrering` to the group registration and records role, membership status, and audit fields.

Invitee removal changes the membership status instead of deleting the invitee registration. Active memberships drive group approval guards. Dropped memberships remain available for detail and audit context.

The public prospect flow rejects existing volunteers and active registrations instead of reusing or duplicating them.

## Consequences

The admin UI can show grouped applicants together while keeping each person's registration and application state separate. This gives a usable v1 flow for "bring a friend" recruitment while preserving the registration history needed for later review.

The model intentionally separates application status from group membership status. A person can have a preserved application row even if their group membership is no longer active.

The production end-to-end flow works, but the approval UX is still easy to misuse because grouped and per-person approval actions currently exist near the same workflow.

## Addendum: Approval UX Discussion

After the feature shipped, we observed a confusing partial state: approving only the inviter through the per-person `Godkjenn` flow can leave the remaining invitee less obvious in the application list. The invitee is not conceptually "dropped" by that action, but the list is anchored around the inviter row, so promoting the inviter first can make the grouped state hard to understand.

The preferred simplification is that active grouped registrations should be approved through one group-level action only. Per-person approval should remain available for standalone applications, but not for active members of a group registration.

Future hardening should:

- Hide or block per-person approval for active grouped applications.
- Rename `Godkjenn alle` to `Godkjenn gruppen`.
- Make group approval atomic and all-or-nothing.
- Group the admin list by `group_id`, not by the inviter row, so partial historical states remain visible.
- Add automated tests for grouped approval, partial-state visibility, dropped members, and direct per-person route access.

## Addendum: Audit and Profile Visibility

Grouped registrations must remain visible after promotion, not only while they are pending applications.

Accepted behavior:

- People who signed up in a group together appear together in the recent registration log.
- A volunteer profile with a corresponding `registrering` entry shows that registration entry, including source, status, group choices, and group membership role/status when present.

No data repair or backfill is required as part of this ADR. This document records the current design and the follow-up direction; it does not itself implement the approval simplification.
