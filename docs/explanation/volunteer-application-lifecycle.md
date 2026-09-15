# The Volunteer Application Lifecycle

The volunteer application rules live in the pure state machine in
`app/domain/volunteer_applications/state_machine.py`. Public prospects, direct
invites, and friend invitees use the same lifecycle. A friend invitation adds
relationship metadata and an informational “start together” note; it does not
change the legal transitions for either application.

## States and Transitions

An application's `status` column holds one of five states, constrained by a
database CHECK:

```mermaid
stateDiagram-v2
    [*] --> new: public signup / invitation
    new --> new: submit_profile
    contacted --> contacted: submit_profile
    trial --> trial: submit_profile
    volunteer --> volunteer: submit_profile
    new --> new: resend_invitation
    new --> contacted: contact
    contacted --> trial: start_trial
    trial --> volunteer: approve
    contacted --> not_volunteer: reject
    trial --> not_volunteer: reject
    volunteer --> not_volunteer: reject
    not_volunteer --> contacted: reopen
    new --> [*]: delete
    note right of volunteer
        Promoted applications remain as history.
        Offboarding detaches promoted_volunteer_id.
    end note
```

Profile submission keeps the current lifecycle state. Trial-shift marking is
legal in the active recruitment states and never changes the application
state; it flips a flag and emits an audit event.

## Public Choices and Promotion

The public form submits a required first choice and an optional second choice.
Personal stores immutable display labels for both choices as application
metadata. A public choice does not always correspond one-to-one with an
operational group: several bar-area choices route to roles under the
Skjenkegruppen parent group.

Only the first choice determines the suggested operational group and role.
Promotion therefore offers the primary placement, not the secondary choice.

## Guards

`approve` requires a submission row — there is nothing to promote without
applicant details. Friend-invited applications do not participate in a shared
approval guard: each application's own state and submission determine whether
it can be approved.

## How a Transition Executes

The workflow coordinator gives every lifecycle action the same shape, and the
unit of work makes the database part atomic by construction:

```mermaid
sequenceDiagram
    participant R as Route
    participant W as VolunteerApplicationWorkflow
    participant SM as state_machine (pure)
    participant Repo as Repository
    participant V as VolunteersService (via VolunteerCreatorProtocol)
    participant DB as Request transaction
    participant SMTP as SMTP

    R->>W: start_trial(application_id)
    W->>SM: application_transition(state, START_TRIAL, context)
    SM-->>W: TransitionResult or IllegalTransition
    W->>V: create_from_application(..., contract_signed=false)
    V->>DB: insert volunteer_records and temporary assignment
    W->>Repo: set trial status and promoted_volunteer_id
    W->>Repo: append_domain_event(...)
    W->>DB: commit_request_session()
    W->>SMTP: profile-completion email for this applicant

    R->>W: approve(application_id, group)
    W->>SM: application_transition(state, PROMOTE, context)
    SM-->>W: TransitionResult or IllegalTransition
    W->>V: create_from_application(..., volunteer_id=promoted_volunteer_id)
    V->>DB: update volunteer record and finalize assignment
    W->>Repo: mark_promoted(invite row)
    W->>Repo: append_domain_event(...)
    W->>DB: commit_request_session()
```

Each applicant's promotion happens in that applicant's request transaction. A
friend who has not submitted cannot block the inviter, and vice versa. Emails
go out only after commit, and every transition appends a `domain_events` row in
the same transaction as the state change. State in columns remains the source
of truth; the log is an audit, not an event-sourcing store (ADR-003).

## Cross-Module Boundary

Trial start provisions the volunteer record and temporary assignment, and
approval reuses that record to finalize the assignment. Both writes go through
`VolunteersService.create_from_application`, reached via
`VolunteerCreatorProtocol` injected in `app/runtime.py`. There is no static
service import between the modules; the owning module performs its own write.
