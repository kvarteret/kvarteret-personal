# Domain logging and analytics implementation spec

Status: implemented for application-owned runtime paths in the current
personal, website, and mobile checkouts. Mobile product analytics remains
disabled until its approved privacy preference is wired. The deployed Vercel
drain/collector remains an external dependency and was not changed because its
owning configuration was not present in the inspected repositories.
Date: 2026-09-10.
Scope: personal (`kvarteret-personal`), samfunnetibergen.no (`samfunnetibergen`),
and the mobile app (`kvarteret-internbevis`). PostHog project: 202551, EU.

## 1. Decision

Production logs should describe meaningful outcomes and actionable problems.
Routine HTTP traffic and successful dependency calls belong primarily in metrics
and sampled traces. Product analytics describes journeys, adoption, and conversion.

A business outcome may legitimately appear in both logs and product analytics.
Define it once at the authoritative boundary and project it into the two sinks
with a shared occurrence ID. Do not implement two independent interpretations of
success. Do not turn every log into an analytics event or every click into a log.

Business state and existing database audit records remain authoritative. PostHog
logs and analytics are diagnostic projections, not a booking ledger or audit store.
Telemetry failure must not turn successful business work into a failed response.

## 2. Verified baseline and source map

Inspected local source at personal `7ff9d12`, website `e1b4a5f`, app `b695590`.
These are checkout observations, not a claim that all three versions are deployed.
Paths below are relative to their named repository unless linked.

| Owner | Current source and behavior |
| --- | --- |
| Personal | [app/observability.py](../../app/observability.py) emits event names as messages, logs every completed request at INFO, and emits operation timings at INFO. Ordinary logger calls become `log.message`. |
| Personal | [workflow.py](../../app/domain/volunteer_applications/workflow.py) owns volunteer transitions and database audit events. Prospect registration is also logged in [volunteer_prospects.py](../../app/api/v1/volunteer_prospects.py), duplicating the workflow outcome. |
| Personal | [email_outbox_service.py](../../app/email_outbox_service.py) emits `email.delivery` with status and retry fields. The sanitizer currently drops allowlisted `email_delivery_id` because the forbidden substring list includes `email`. |
| Personal | [mobile_card.py](../../app/api/v1/mobile_card.py) exposes `/api/v1/mobile-card/me`; `/api/v1/users/me` is absent from the current router. [telemetry.py](../../app/api/v1/telemetry.py) is an authenticated web-client-error endpoint, not a general mobile telemetry receiver. |
| Website | `apps/web/src/lib/observability.ts` emits stable event names as bodies and always uses INFO. It already injects active trace context. |
| Website | `apps/web/src/features/booking/actions/submit-room-booking.ts` emits `booking.submitted` after a successful Crescat response. `components/BookingForm.tsx` separately captures `room_booking_submitted` in the browser. Server and browser both have rejection instrumentation. |
| Website | `apps/web/src/features/karaoke/actions/submit-karaoke-booking.ts`, `components/KaraokeForm.tsx`, and `apps/web/src/lib/booking/telemetry.ts` implement related submission/failure analytics. Apply the same contract to karaoke. |
| Website | `apps/web/src/app/api/volunteer-prospects/route.ts` proxies to personal but names its success `volunteer.application.submitted`; this is prospect registration, not the later application transition. |
| App | `src/features/auth/data/authRepository.ts` requests access codes, creates mobile-card sessions, fetches `me?include_role_history=true`, caches cards, and persists renewed tokens. No PostHog dependency or existing PostHog calls were found in the inspected app source/package manifest. Mobile telemetry is new work, not a configuration toggle. |
| App/website | `src/features/dashboard/data/eventsRepository.ts` in the app calls the generated samfunnet events API client. Website `apps/web/src/features/events/server/public-events.ts` owns public event reads backed by Sanity. Personal does not own that public events API. |

Recent live samples showed successful polling, media requests, timing records,
platform wrappers, and Sanity connection notices. A browser sample contained 16
connection-success messages and two CORS warnings. These samples motivate the
policy; they are not a complete traffic census or a forecast of savings.

## 3. Routing policy: logs, analytics, traces, or audit

| Question or occurrence | Operational log | Product analytics | Other record |
| --- | --- | --- | --- |
| Room/karaoke request accepted by Crescat | INFO, every observed acceptance | Server-owned conversion | Crescat remains booking authority |
| Booking confirmed | INFO only after authoritative confirmation | Conversion if confirmation integration exists | Booking authority |
| Form opened, step completed, field validation shown | No | Browser journey events | None |
| Booking rejected by business rules | INFO with bounded reason | Server rejection outcome; client feedback is a separate event | Trace |
| Submission timed out or dependency failed | WARN if recoverable, ERROR if terminal | Failure outcome where used by conversion analysis | Trace/error tracking |
| Volunteer prospect registered/application approved | INFO, every committed transition | Selected recruitment milestones | Existing transactional audit |
| Email queued/provider accepted/retry scheduled/failed | INFO/WARN/ERROR by outcome | No by default | Existing delivery state and attempts |
| Initial mobile identity resolved/session created | INFO | Session creation/login success only | Trace |
| Repeated healthy card refresh | DEBUG, not exported normally | No | Latency/error metrics and sampled trace |
| Card displayed, event opened, feature used | No | App interaction, if enabled | None |
| App falls back to cached card | INFO once per degraded episode | No by default | Client diagnostic context |
| Admin changes volunteer/account state | INFO with actor/action/outcome | No by default | Existing audit, where supported |
| Healthy HTTP completion, polling, media/analytics proxy request | No default INFO export | No | Request metrics, sampled traces |
| Unexpected platform failure | WARN/ERROR | No | Error tracking/platform diagnostics |

Add a product event only when its catalog entry states the product question it
answers. For example, recruitment milestones answer where applicants drop out;
email retries ordinarily answer an operational question. Do not add analytics
solely because a domain log exists.

## 4. Booking semantics and ownership

Use `booking.request.accepted` with message **“Room booking request accepted by
Crescat”** (or “Karaoke booking request accepted by Crescat”). Include
`booking_kind=room|karaoke`. Current HTTP success establishes request acceptance;
it does not establish that a room is reserved or approved.

Reserve `booking.confirmed` / **“Room booking confirmed”** for a verified status
transition from the booking authority. Do not introduce it until a confirmation
callback or reconciliation read has been verified. Confirmation integration is
outside the initial implementation scope. Thus “room booked” is not a valid
label for the current acceptance event.

The server integration boundary owns acceptance, rejection, and dependency
failure. The browser owns form interactions and, if useful, a separate
`booking_success_shown` event. A missing browser response does not erase a
server-observed acceptance. Honeypot responses must produce no conversion.

Canonical proposed outcomes:

| Event | Trigger | Message |
| --- | --- | --- |
| `booking.request.accepted` | Crescat returns the verified accepted response | Room booking request accepted by Crescat |
| `booking.request.rejected` | Server rejects a validly parsed request for a business rule | Room booking request rejected: time unavailable |
| `booking.request.failed` | Known terminal failure without acceptance | Room booking request could not be submitted |
| `booking.request.outcome_unknown` | Timeout/disconnection after dispatch; acceptance cannot be determined | Booking request outcome could not be confirmed |

Do not describe an ambiguous timeout as definitely rejected or automatically
resubmit an external booking to repair telemetry. Reconciliation requires an
actual provider identifier/idempotency contract. The current client-generated
`booking_submission_id` is correlation, not proof of backend deduplication.

## 5. Shared event contract

Implement small typed helpers in Python, website TypeScript, and app TypeScript.
Maintain a versioned catalog with event name, approved message, owner, trigger,
severity, required/optional fields, analytics projection, and retention class.
Use shared contract fixtures across implementations; do not require a new central
event service or framework.

Required envelope: `event`, `schema_version=1`, `event_id`, `occurred_at`,
`service`, `environment`, `outcome`, and approved human-readable `message`.
Add `trace_id`, `span_id`, and validated `request_id` when available. Resource
attributes carry deployment/app version. Never invent trace IDs for untraced work.

Optional, explicitly typed domain fields: `registration_id`, `volunteer_id`,
`booking_submission_id`, `booking_kind`, `email_delivery_id`, `template_key`,
`operation_id`, `attempt_id`, `attempt_no`, `reason_code`, `failure_stage`,
`error_category`, `duration_ms`, and provider HTTP status. Do not overload one
`status` field with HTTP status, business state, and delivery state.

Example log body: **“Volunteer application approved”**.
Attributes: `event=volunteer.application.approved`, `registration_id=…`,
`volunteer_id=…`, `outcome=success`, `event_id=…`, `trace_id=…`.
The message must be understandable without expanding JSON. Export the readable
body as the OTel log body and machine fields as attributes, rather than a JSON
string containing another message field.

Messages come from reviewed templates. Never restore arbitrary raw logger
messages or interpolate submitted names, descriptions, tokens, URLs, or response
bodies. Replace application-owned `log.message` call sites with catalog events;
preserve safe exception category and trace linkage. Review legacy library output
separately instead of pretending every generic message is useful.

## 6. Occurrence identity, retries, and delivery guarantees

One logical transition has one event ID shared by log and analytics projections.
Reuse it on export retry. Use an existing committed domain-event ID, namespaced
by service and event type, when available; otherwise create an occurrence UUID.
An operation ID groups attempts; an attempt ID identifies each actual attempt.
Neither a volunteer ID nor a trace ID is an occurrence ID.

Emit committed-state successes only after commit. Idempotent request replay must
not create another business conversion. Logs describing replay may be DEBUG.
Keep separate retry-attempt diagnostics; count unique accepted operations in
conversion reporting. A genuinely new booking is a new operation even when the
form values match.

Use the occurrence ID as a deduplication property in both sinks; during
implementation verify the supported PostHog ingestion deduplication mechanism
before relying on it. Acceptance tests must cover duplicate delivery. Do not
claim distributed exactly-once delivery. Queries must be able to count unique
occurrences regardless of transport duplicates.

Initial reliability target: business audit/delivery records retain their existing
durability; logs and analytics are best-effort, unsampled for selected business
outcomes, and may have delivery gaps. Independent sink failures cannot prevent
the other sink being attempted. Flush through supported runtime lifecycle hooks,
not background daemons. Track exporter failures without recursive logging.
Do not add a telemetry outbox in phase one. If complete conversion accounting
later becomes a requirement, introduce an explicit durable projection/outbox
design rather than treating PostHog as the ledger.

## 7. Work packages

### Personal

1. Extend `emit_event`/formatter with the catalog, approved messages, and typed
   severity. Correct field validation so explicitly approved identifiers such as
   `email_delivery_id` survive; retain rejection of actual email addresses and
   secrets. Add dedicated tests for both cases.
2. Replace `volunteer.lifecycle` plus status with explicit transition events:
   `volunteer.prospect.registered`, `volunteer.application.submitted`,
   `volunteer.application.approved`, `volunteer.application.rejected`,
   `volunteer.application.deleted`, and invitation/trial-shift transitions
   supported by the state machine. Emit only on actual committed changes.
3. Remove prospect success emission from the API handler; workflow owns it.
   Preserve existing database audit semantics. Never export its arbitrary payload.
4. Replace `email.delivery` labels with `email.delivery.queued`,
   `email.delivery.accepted`, `email.delivery.retry_scheduled`, and
   `email.delivery.failed`. “Accepted by mail server” does not imply inbox delivery.
5. Instrument mobile-card session creation, renewal, rejection, and identity
   resolution at the service boundary. “Authenticated session matched to
   volunteer” requires both authentication and successful volunteer resolution.
   Other supported subject types must have truthful messages/subject fields.
   A session rejection does not by itself imply an unlinked volunteer account.
6. Emit initial resolution/session creation at INFO, normal repeated reads at
   DEBUG. Retain unsampled failures, but deduplicate repeated identical client
   refresh failures into an episode plus counters. Normal expiry is INFO;
   failed persistence or unexpected backend failure is WARN/ERROR.
7. Preserve admin action/actor/outcome in readable templates. Move ordinary
   `app.operation.timing` and HTTP success logs to metrics/spans.

### Samfunnetibergen.no

1. Extend `emitOperationalEvent` with the same catalog contract and severity;
   current INFO-only emission cannot express failures properly.
2. Apply the booking contract to room and karaoke server submitters. One helper
   projects the authoritative outcome to log and selected analytics event.
3. Move acceptance analytics from browser callbacks to the server boundary.
   Retain form-start/step/UI feedback events in the browser. Separate client-side
   validation feedback from authoritative server rejection to prevent double counts.
4. Rename the volunteer proxy success to `volunteer.prospect.forwarded`, DEBUG
   by default, or represent it only as a span. Personal alone owns
   `volunteer.prospect.registered`; the website must not claim the later
   `volunteer.application.submitted` transition.
5. Filter the exact routine Sanity connection-success message from production
   console ingestion. Preserve CORS/connectivity warnings; coalesce repeated
   warnings per episode. This is an ingestion change, not a change to Sanity data.
6. Suppress routine now-playing, static/media, middleware, redirect, and analytics
   proxy successes. Preserve endpoint health through metrics.

### Mobile app

1. Add a typed observability adapter under `src/core/observability/`, with domain
   calls from auth repositories/services and UI analytics from view-model/UI
   boundaries. No blanket capture of console output, fetch bodies, or storage.
2. Personal owns authenticated backend outcomes. App owns
   `mobile_card.displayed` (analytics), `mobile_card.cache_fallback_started`
   (INFO), `mobile_card.cache_fallback_recovered` (INFO),
   `mobile_card.response_invalid` (ERROR),
   `mobile_card.session_token_persist_failed` (WARN), and local logout outcomes.
   Cached-card display must never be described as fresh server validation.
3. Correlate requests with validated request/operation IDs and trace context
   where supported. No token, email, card payload, or login deep-link value in
   telemetry. Do not send duplicate “login succeeded” conversions from app and
   personal; app may separately record that the success UI was displayed.
4. Product analytics uses the supported React Native PostHog SDK, selected and
   verified at implementation time, behind the existing/product-approved privacy
   preference. Default to disabled until that preference is explicitly wired.
5. Operational diagnostics use a dedicated bounded personal ingestion endpoint,
   not an embedded private ingest credential and not the existing admin-auth web
   error endpoint. Define a strict catalog/schema, request size limit, rate limit,
   source=client, and authentication where available. Allow only coarse approved
   pre-auth error categories anonymously. Treat all client claims as untrusted;
   they cannot emit authoritative business conversions or trusted volunteer IDs.
6. Bound the local diagnostic queue to 100 records/24 hours, drop oldest when
   full, retry with backoff, and flush when online without delaying navigation.
   Store only sanitized records. Emit fallback/recovery once per episode, not
   every rerender or poll. Respect collection preferences before enqueueing.

### Shared platform ingestion

Locate the deployed Vercel drain/collector configuration before editing it; its
owner was not established from these source paths. This is a required deployment
dependency, not assumed to live in any particular repository.

Keep direct application OTel as the canonical application log path. Drop drain
copies only when they can be reliably identified as records covered by that path.
If duplicate matching is uncertain, first hide them from the domain view and
measure coverage before dropping. Preserve platform-only startup crashes,
timeouts, and failures occurring before application telemetry initializes.

Drop known healthy `vercel.request.completed` records and known routine
`vercel.runtime.log` wrappers. Never drop an unknown runtime message solely
because the HTTP response is 200: application errors can occur within it.
Keep unexpected 5xx, timeouts, and actionable warnings. Expected redirects,
expired sessions, validation responses, and bot 404/429 traffic are not all ERROR;
use aggregate security/traffic metrics and sampled diagnostics for repetitive noise.

## 8. Analytics migration and privacy

Retain existing `room_booking_submitted` / `karaoke_booking_submitted` analytics
names initially, mapped from server `booking.request.accepted`, to preserve
dashboards. Add `schema_version=1`, `source=server`, and `domain_event_id`.
Stop browser emission of those names in the same release; cached clients require
a migration filter and deduplication by submission ID. Verify no dashboard counts
both the new canonical event and a compatibility alias. Preserve historical data;
document the cutover timestamp and source change in conversion dashboards.

Server analytics must honor the applicable collection preference; moving capture
server-side must not bypass a user's choice. If permitted, forward only the
necessary pseudonymous analytics/session identifier, validated and bounded.
Do not use a shared `anonymous` person to infer unique users or personal funnels.
Without permitted identity, report aggregate outcomes and keep them separate from
user-linked funnels. Operational logging remains a separately documented policy.

Explicitly allowlist properties per sink. Operational IDs are not automatically
approved analytics properties. Exclude names, emails, phone numbers, free-text
booking descriptions, form bodies, credentials, raw URLs/query strings, and
unreviewed audit payloads. Use route templates and bounded reason codes. Keep
high-cardinality IDs out of metric labels. Do not broaden retention/access as
part of this migration; inventory current settings before rollout.

## 9. Severity, visibility, and performance defaults

- INFO: meaningful committed success, expected business rejection, or recovery.
- WARN: transient failure, retry scheduled, degraded operation requiring attention.
- ERROR: terminal unexpected failure or unusable response.
- DEBUG: normal refreshes, cache hits, transport acknowledgments, detailed timing.

Initial slow-request threshold: 2 seconds for application endpoints, with explicit
route overrides reviewed after baseline collection. This is a starting policy,
not a universal service-level objective. Keep request count, latency, error-rate,
and cron-last-success metrics independently of log sampling. Sample ordinary
success traces at 1% initially; document the actual sampler and its ability to
retain slow/error traces before claiming those are complete. Never sample away
the selected domain outcome logs merely because their trace was not retained.

Provide saved views for domain activity, failures/degradation, and platform
diagnostics. Default domain activity shows readable messages and allows filtering
by service, event, registration/booking/delivery ID, and trace. Alert on actionable
failure rates, terminal delivery failure, and missing expected cron activity;
do not alert on every successful business event or ordinary rejected form.

## 10. Rollout and acceptance criteria

1. Inventory current event producers, analytics dashboards, collector ownership,
   privacy controls, and baseline volume by event/service over a representative
   period. Confirm deployed source differs from neither assumptions nor contract.
2. Implement catalog/helpers and contract tests, then domain outcomes in personal
   and website. Validate in preview without changing production ingestion.
3. Cut over booking analytics with dashboard migration and old-client handling.
4. Implement app adapter/receiver; regenerate and verify OpenAPI if personal adds
   the proposed receiver. Older mobile versions must continue functioning.
5. Enable deduplication and noise filtering only after source coverage is proven.
6. Compare production volume and domain coverage for seven days. Target zero
   routine success notices in the default domain view and no duplicate conversion
   for a logical transition; do not promise a percentage reduction beforehand.

Required verification scenarios:

- Room and karaoke acceptance: one canonical server outcome, readable log, one
  analytics conversion when permitted, matching occurrence/submission IDs.
- Honeypot, validation rejection, retry, response timeout, duplicate export,
  and cached old browser: no false confirmation or doubled conversion.
- Personal registration through website: one committed registration outcome;
  proxy span links to it; no false application-submitted transition.
- Approval rollback produces no success log; committed approval has audit and
  readable outcome. Delivery IDs survive redaction and link queued/retry/accepted.
- Missing/expired session, fresh card, cached fallback, malformed response,
  token-save failure, and recovery produce distinct truthful app outcomes.
- PostHog unavailable or one sink throws: business request remains successful,
  other sink still attempted, bounded telemetry delivery does not recurse.
- Sanity success filtered while CORS warning remains; platform crash survives
  even with no application log; slow request survives ordinary success filtering.
- Secret/PII fixtures cannot reach any sink; denied analytics preference produces
  no analytics capture; untrusted clients cannot forge server-domain outcomes.

Roll back through separate flags for new analytics ownership and ingestion
filtering. Never re-enable both browser and server conversion owners together.
Keep the readable domain logs during a noise-filter rollback where possible.

## 11. Explicit boundaries for later implementation

This spec decides the log-versus-event policy, authoritative owners, initial
catalog, migration, and acceptance criteria. It does not approve adding a booking
confirmation integration, adopting event sourcing, replacing database audit,
or deploying changes now. Runtime implementation must verify current SDK/export
APIs, the deployed collector, privacy preference wiring, and external provider
acceptance semantics before selecting exact configuration and dependency versions.
