# Domain logging and analytics: revised implementation plan

Status: proposed remediation and staged release plan; not a claim of deployment
or completed acceptance testing. Date: 2026-09-10.

This revision supersedes the previous three-repository rollout. Release first to
`kvarteret-personal` and `samfunnetibergen`. Do not release the mobile PR or require
an app update. Implementation and deployment are separate steps; this document
alone does not authorize a production deployment.

## 1. Scope and verified starting point

The review inspected Personal PR #56 at `a1fc843`, Website PR #138 at `1a24cae`,
and Mobile PR #30 at `53072cc`. These are source snapshots, not deployed versions.
A second source check found Personal at `e424d5a` and Website at `be15d90`;
Mobile remains at `53072cc`. Intervening changes were inspected: the new Personal
receiver has been removed, logger/commit support has begun, and website acceptance
capture now retains the legacy names behind `BOOKING_ANALYTICS_OWNERSHIP=server`.
These changes are partial progress, not acceptance evidence. In particular, the
browser conversion removal still needs the staged-ownership protocol below.
Refresh PR heads before implementation and preserve concurrent work.

| Surface | First release | Deferred |
| --- | --- | --- |
| Personal | Readable domain logs; transaction correctness; logger wrapper; isolated sinks; email and volunteer outcomes; backend auth/mobile-card operational outcomes | New mobile diagnostic endpoint and its OpenAPI additions; new recruitment/login product analytics pending explicit selection and collection policy |
| Website | Room/karaoke authoritative logs; pseudonymous server booking conversion migration; truthful volunteer proxy event; application-owned noise controls | Booking confirmation integration; unverified collector changes |
| Mobile | Existing released app continues using its existing API contract | All of PR #30: adapter, queue, privacy UI, PostHog SDK and new diagnostics transport |
| Platform | Inventory collector ownership, delivery, dashboards, access and retention; preserve platform failures | Destructive filtering until duplicate coverage is demonstrated |

Personal still owns backend mobile-card authentication. Keeping its operational
logs in scope does not introduce mobile product analytics or depend on new app
instrumentation. Personal recruitment/session analytics is an explicit reduction
from the original plan, not a completed work package: define those product
questions and privacy requirements in a separate follow-up before enabling them.

Verified source anchors:

- Personal [observability](../../app/observability.py) and
  [OTel export](../../app/telemetry.py): catalog/emission and handler boundaries.
- Personal [volunteer workflow](../../app/domain/volunteer_applications/workflow.py)
  and [email outbox](../../app/email_outbox_service.py): transaction ownership.
- Personal [mobile-card API](../../app/api/v1/mobile_card.py): existing API and
  legacy client route retained; the new receiver was removed in the follow-up.
- Website [booking projection at reviewed head](https://github.com/kvarteret/samfunnetibergen/blob/1a24cae21714e9baaa8088d6857adfa9782c7461/apps/web/src/lib/booking/telemetry.ts):
  original migration defects; the follow-up restores names and adds an ownership flag.
- Website [operational helper at reviewed head](https://github.com/kvarteret/samfunnetibergen/blob/1a24cae21714e9baaa8088d6857adfa9782c7461/apps/web/src/lib/observability.ts):
  readable bodies exist, but the complete typed contract is still required.
- Follow-up source: [Personal commit changes](https://github.com/kvarteret/kvarteret-personal/compare/a1fc843e29e111f67675d801b888350d72b47f04...e424d5a5492c8bbd9185acd2e266224ac2eb4674)
  and [website commit changes](https://github.com/kvarteret/samfunnetibergen/compare/1a24cae21714e9baaa8088d6857adfa9782c7461...be15d9038cd7ab0869c2833fb2da570c0e7c6424).
- Mobile [queue at reviewed head](https://github.com/kvarteret/kvarteret-internbevis/blob/53072cc2b6e0227da45b901d4de4e453e21a0ebf/src/core/observability/index.ts):
  retain the review findings for the later release.

## 2. Design decisions

Business state, existing database audit records, and Crescat remain authoritative.
Telemetry is a best-effort projection. Do not introduce event sourcing, a new
central event service, a telemetry outbox, or distributed exactly-once claims.

Extend the application logger through a small wrapper/adapter. Proposed Python
usage:

```python
logger = get_domain_logger(__name__)
logger.event("auth.login.failed", reason_code="account_not_found")
```

The catalog supplies approved message, severity and outcome. Callers supply only
typed domain fields and, where available, an existing committed occurrence ID.
They should not repeat `logging.WARNING`, message text and failure outcome for
an event whose catalog already defines them. Use an equivalent typed API on the
website; a compatibility `emit_event`/`emitOperationalEvent` shim may delegate to
the same implementation while call sites migrate.

Do not globally replace third-party loggers or patch standard logging methods.
Preserve normal logging interoperability, logger names, caller location and safe
exception category/trace linkage. Review remaining application-owned free-form
calls; do not export raw messages or arbitrary exception/audit payloads.

Create the occurrence once, before any sink-specific filtering. Logging level
changes must not suppress an independently enabled analytics projection.
Formatters render an existing occurrence; they must never generate different
IDs/timestamps when different handlers format the same record.

## 3. Work package A: contract and failure isolation

Owners: Personal and website, implemented before migrating domain call sites.

1. Define versioned catalogs with event name, owner, trigger, approved message,
   severity, outcome, required/optional typed fields, per-sink property allowlists,
   analytics mapping/product question, and retention class. Unknown event names
   and invalid fields fail contract tests. Runtime validation failure drops the
   invalid telemetry safely and increments a bounded diagnostic counter. Validate
   one immutable occurrence before projecting it; analytics must not reconstruct
   unchecked input when operational validation rejects the occurrence. Per-sink
   allowlists then select properties from that validated occurrence.
2. Required occurrence envelope: `event`, `schema_version=1`, `event_id`,
   `occurred_at`, `service`, `environment`, `outcome`, and readable message.
   Add real trace/span context and validated request ID when available. Deployment
   and application versions belong in resource attributes. Never invent traces.
3. Use namespaced committed domain-event IDs where available; otherwise generate
   an occurrence UUID. Missing optional IDs must not overwrite generated IDs with
   null. Retrying an export preserves the occurrence ID and timestamp. Keep
   operation/attempt identifiers distinct from occurrence and subject identity.
   Catalog outcome, service, environment and schema version cannot be overridden
   through caller fields. Accept occurrence identity/time only through dedicated,
   validated parameters. Require timezone-aware UTC times and finite numbers;
   enforce field types, required fields, enum membership and size bounds.
4. Allow only reviewed values and bounded enums for reasons, categories and
   outcomes. Explicitly allow `email_delivery_id` while rejecting email addresses,
   credentials, free text, raw URLs, form/card bodies and unreviewed audit payloads.
   Operational properties are not automatically approved analytics properties.
5. Isolate each handler/exporter and each selected analytics sink. A synchronous
   throw, rejected promise, or exporter outage must not change a business response
   or prevent another sink from being attempted. Catching around the overall
   logger call alone is insufficient when one handler prevents later handlers.
6. Use a two-second total telemetry flush budget per request, shared across sinks,
   with independent attempts. On the website register delivery through the supported
   post-response lifecycle hook; do not await a two-second analytics race inside
   the booking action. On Personal retain a bounded invocation-lifecycle flush
   after the business response. Configure transport timeouts/cancellation as well:
   `Promise.race` alone does not cancel delivery. Reuse the original occurrence
   on any SDK retry; never retry the business operation for a telemetry failure.
   Verify the pinned SDK/runtime hooks rather than assuming background work survives.
7. Count validation/export failures using fixed reason keys, exported through the
   metric path. Process-local counters are diagnostic state, not durable monitoring.
   Test that the counter is externally observable in preview. If that sink is also
   down, rely on platform/exporter health checks; never recursively log failures
   through the broken exporter or claim complete outage accounting.
8. Store shared envelope/redaction fixture vectors in each repository, with the
   same contract version and recorded digest. Both test suites must execute them;
   merely adding matching JSON files is insufficient. Keep service-specific event
   catalogs separate. Compare the shared fixture digest as part of the coordinated
   release check; neither repository's ordinary CI needs a sibling checkout.

Exit evidence: both implementations pass the same envelope/redaction fixtures;
a deliberately failing sink does not prevent the other sink or business success;
repeated formatting/export preserves identity and readable OTel body/attributes.

## 4. Work package B: Personal domain corrections

1. Migrate application-owned domain calls to the wrapper. Remove submitted login
   identifiers from telemetry. Preserve actor/action/outcome for admin changes in
   reviewed templates, with approved actor IDs as structured fields.
2. Emit volunteer prospect registration, submission, profile completion,
   invitation, contact/trial, approval, rejection, restoration and deletion only
   for actual transitions supported by the state machine. Replays/no-ops produce
   no new success occurrence. Workflow owns these outcomes; API/proxy handlers
   must not duplicate them.
3. Reuse committed audit-event IDs without exporting audit payloads. Emit after
   commit and before unrelated fallible post-commit side effects where possible.
   Rollback must produce no committed-success log.
4. Stage `email.delivery.queued` with its owning database transaction, never in
   an unscoped process/context-global queue. Use session/transaction-owned pending
   records, drained once after successful commit and discarded on rollback or
   session disposal. A second transaction in the same request starts empty;
   nested sessions and concurrent requests cannot drain each other's records.
   Cover explicit commits, dependency-managed commits and script/session scopes.
   Savepoint rollback must discard only its pending records; release to the outer
   transaction must not emit before the outer commit. Keep the database coordinator
   generic: it must not import email-domain services to flush their events.
   Without a real commit boundary, do not claim persistence or emit queue success.
   Use a stable queued-event ID derived from the delivery ID, and create its
   occurrence time when commit succeeds. Do not commit early solely to log.
   Inspect every enqueue caller, including non-volunteer flows.
5. Keep distinct queued, mail-server accepted, retry-scheduled and terminal-failed
   events. Preserve delivery/attempt IDs. Provider acceptance is not inbox
   delivery; deferred dispatch is not automatically a terminal delivery failure.
6. Keep truthful backend mobile-card session/subject outcomes. Normal expiry is
   INFO; normal reads/renewals are DEBUG; unexpected failures remain actionable.
   Do not equate a rejected session with an unlinked volunteer or a trial/review
   subject with a volunteer. Emit committed-state successes after commit.
7. Remove the new `/api/v1/mobile-card/client-events/diagnostics` route and its
   request schema from the first-release change. Preserve the pre-existing
   `client-events/session-logout` route and released-client compatibility. Keep
   its accepted input shape compatible and sanitize its output centrally; do not
   make it depend on the deferred receiver. For the legacy route, derive source
   as `client` server-side, discard raw messages/cached user IDs, and map both
   `credentials_missing_after_login` and `session_invalidated` to bounded failure
   diagnostics (neither is successful logout). Keep client claims out of trusted
   backend session outcomes. Verify representative released-app payloads against
   the base contract; do not tighten old field limits as an incidental migration.
   Regenerate OpenAPI and verify there is no new diagnostics route or unintended
   breaking change. Treat the follow-up receiver removal as work to verify, not
   a reason to remove an unrelated released endpoint.
8. Separate unrelated offline-write settings and behavior changes from this
   observability release unless independently required and reviewed. Restore
   existing environment variable names where the telemetry PR renamed them
   (including the website Slack webhook), or preserve an explicit compatibility
   alias. Logging changes must not silently disable an existing integration.

Exit evidence: committed transitions produce one readable occurrence, rollback
and replay produce none, queued logs follow the real commit, old mobile requests
still work, and injected logging failures do not alter business results.

## 5. Work package C: website outcomes and analytics migration

### Authoritative outcomes

Apply the same server-boundary helper to room and karaoke submissions:

| Domain event | Trigger | Severity | Acceptance analytics |
| --- | --- | --- | --- |
| `booking.request.accepted` | Verified Crescat acceptance response | INFO | Room: `room_booking_submitted`; karaoke: `karaoke_booking_submitted` |
| `booking.request.rejected` | Validly parsed request rejected by a business rule | INFO | None; any rejection analytics needs an explicit separate mapping |
| `booking.request.failed` | Known failure without acceptance | WARN if recoverable; ERROR if terminal | None |
| `booking.request.outcome_unknown` | Dispatch occurred but acceptance cannot be determined | WARN | None |

Severity variants must be bounded catalog policy, not arbitrary call-site levels.
Use readable room/karaoke-specific messages. Do not emit `booking.confirmed`, call
acceptance a reservation, or automatically resubmit ambiguous requests. Verify
provider response semantics against the current integration before release.

Honeypot responses emit no conversion. Browser form/step/validation events remain
journey signals. A separate `booking_success_shown` may describe UI feedback, but
must not share conversion semantics. Audit existing failure/rejection captures in
both browser and server so old and new producers do not independently count the
same authoritative outcome. Rename the volunteer proxy success to
`volunteer.prospect.forwarded` at DEBUG; Personal owns registration.

### Existing collection behavior and pseudonymous identity

1. Preserve the current pseudonymous analytics implementation for the Personal
   and website first release. Do not add a consent banner, explicit opt-in,
   consent payload field, or consent prerequisite for server analytics. Missing
   explicit consent is not a reason to suppress collection or block this release.
2. Inventory existing pseudonymous identifiers and collection settings. Carry only
   validated, bounded pseudonymous context needed by the server projection; do
   not introduce direct personal identifiers or broaden collection. Preserve any
   existing explicit opt-out behavior when moving capture server-side.
3. Read the existing PostHog pseudonymous identity for the configured project;
   do not select the first arbitrary `ph_*` cookie. Bound cookie parsing and the
   extracted ID (maximum 256 characters), accept only the actual SDK-generated
   identifier formats verified in fixtures, and reject free text/direct identifiers.
   Cookie IDs are untrusted correlation, never authentication or domain identity.
   Do not forward raw cookies. Missing/invalid identity uses the existing
   `anonymous` aggregate fallback with `$process_person_profile=false` and
   `identity_scope=aggregate`; valid identity uses `identity_scope=pseudonymous`.
   Exclude aggregate records from unique-person/funnel reports. This introduces
   no new consent gate, tracking identifier, identification call or collection UI.
4. Acceptance analytics keeps the existing event names and carries
   `schema_version=1`, `source=server`, `domain_event_id`, `booking_submission_id`,
   and approved bounded properties. Preserve existing dashboard properties only
   after per-property review; update dashboards for deliberately removed fields.

### Identity, old clients and cutover

- Verify the supported PostHog ingestion deduplication mechanism for the selected
  SDK/API and wire it to the occurrence ID. A custom `event_id` property alone is
  not proof of ingestion deduplication. Test duplicate delivery and query unique
  occurrences regardless of transport duplicates.
- A booking submission ID is correlation, not a Crescat idempotency guarantee.
  Do not collapse genuinely new bookings because their field values match. Review
  how a new operation gets a new submission ID and how attempts reuse correlation.
- Build the canonical dashboard/query migration before enabling server capture.
  Before the recorded cutover, count legacy events; after cutover, count only
  server-owned schema-v1 acceptance events. Exclude legacy browser copies after
  cutover, including cached old clients, and audit uniqueness by submission ID.
  Investigate repeated authoritative acceptances rather than hiding distinct
  provider operations through indiscriminate deduplication. Use recorded ownership
  intervals, not the current flag, to select historical sources on rollback. Count
  distinct domain occurrence IDs in server intervals; keep pre-cutover historical
  methodology documented rather than claiming retroactive deduplication where
  old events lack correlation.
- Keep `BOOKING_ANALYTICS_OWNERSHIP` server-controlled with modes `legacy`,
  `server`, and `disabled`; default to `legacy` while staging. Resolve it once per
  submission and return an optional top-level `analytics_owner` on the booking
  result, preserving the existing `ok`, numeric `value`, and `error` fields. Do
  not change the public Personal API for this website-only action metadata.
- Updated browser behavior is deterministic: on real success, emit the existing
  conversion name only when the result says `legacy` (or lacks the marker because
  an old server answered); for `server` or `disabled`, emit no conversion. Continue
  separate UI feedback as appropriate. Honeypot exits before either capture.
  Server mode captures acceptance regardless of whether the browser receives the
  response. It returns `server` even if export fails: browser fallback would create
  ambiguous duplicate ownership. The marker reflects ownership, not delivery.
- Ship that browser/server protocol with legacy ownership first. Check new
  browser/old server and old browser/new server combinations. Enable server mode
  only after lifecycle delivery, context handling and reporting filters pass.
  In-flight requests keep the ownership resolved when they began; a flag change
  cannot give their two projections different owners.
- Cached old browsers ignore the marker and may still emit legacy conversions.
  These transport copies are expected; the canonical reporting filter above must
  exclude them in server-owned reporting intervals. Record immutable ownership
  intervals, deployment versions and boundary gaps. Do not promise an atomic
  deployment or lossless accounting for in-flight requests on an old deployment.
  A rollout boundary may have a documented gap; it must not double-count outcomes.
- Rotate the browser submission ID after a successful booking when starting a
  genuinely new booking. Retain it across attempts of the same unresolved
  operation; do not automatically retry an unknown outcome. A changed/reused
  client ID never proves provider idempotency. Count unique server occurrence IDs,
  using submission IDs to investigate duplicate producers, not to merge separate
  accepted provider operations.

Exit evidence: room/karaoke each produce one readable server acceptance and one
canonical conversion in server mode under the existing collection settings, with
matching occurrence/submission IDs in controlled delivery tests. Production
telemetry remains best-effort and may have delivery gaps. No explicit consent is required. Honeypots, rejections
and ambiguous outcomes produce no acceptance conversion.
Cached clients and duplicate exports do not double-count canonical conversions.

## 6. Work package D: noise, metrics and deployment dependencies

- Replace routine INFO request/timing output with verified request count, latency,
  error-rate and operation metrics/spans. Do not simply turn timing helpers into
  no-ops without preserving the signals they supplied. Keep high-cardinality IDs
  out of metric labels and retain cron-last-success monitoring.
- Initial ordinary success trace sampling is 1%, not the reviewed Personal 10%.
  Document parent sampling behavior and the actual sampler's limitations. Ensure
  slow requests (initial threshold two seconds, with reviewed overrides) remain
  visible through an explicit slow diagnostic/metric path independent of head
  sampling. Do not claim head sampling retains all slow/error traces. Selected
  domain logs remain unsampled regardless of the trace decision.
- Suppress known routine successes for polling, media, redirects and analytics
  proxies. Do not classify all 4xx/expired sessions as errors. Preserve actionable
  failures and aggregate repetitive traffic/security signals.
- Identify production Sanity console-ingestion ownership before filtering its
  exact connection-success message. Keep CORS/connectivity warnings and coalesce
  repetitions by episode where that pipeline supports it.
- Locate deployed Vercel drain/collector configuration and owner. Direct app OTel
  is the canonical application-log path. Hide suspected duplicates in the domain
  view first; drop drain copies only after coverage is proven. Never drop unknown
  runtime output merely because the HTTP status is 200. Preserve startup crashes,
  timeouts and failures before app telemetry initializes.
- Inventory PostHog project 202551/EU destinations, access, retention, dashboards
  and baseline volumes; verify these against deployed settings. Add domain,
  degradation and platform views and actionable rate/terminal-failure/cron alerts.
  Do not broaden retention/access as part of this change.

Collector changes are independently gated. A logging-only application release may
proceed with ingestion unchanged if application acceptance passes; it must not be
reported as completion of platform noise filtering or the analytics cutover.

## 7. Required acceptance matrix

| Scenario | Required result |
| --- | --- |
| Room and karaoke accepted | Approved readable body; shared log/analytics occurrence; existing conversion name and required migration properties |
| No explicit consent supplied | Existing pseudonymous collection continues; no new consent UI, field or gate |
| Pseudonymous context absent/malformed | Aggregate fallback, no raw/unvalidated identity exported, no new consent gate |
| Existing opt-out active | Existing suppression preserved across the ownership change; no new opt-in UI |
| Honeypot, validation, business rejection | No acceptance conversion; UI feedback distinct from server rejection |
| Timeout after dispatch | Unknown outcome; no false rejection/confirmation or telemetry-driven resubmission |
| Duplicate export, retry, cached old browser | Stable occurrence on export retry; canonical queries count no duplicate conversion |
| Genuine new booking with identical values | New operation; not incorrectly deduplicated by form content |
| Prospect through website, idempotent replay | One committed Personal event; linked proxy trace; no false application submission |
| Approval/email enqueue rollback | No committed-success or queued event; audit/business transaction unchanged |
| Committed email queue/retry/acceptance/failure | Readable distinct outcomes with preserved delivery and attempt correlation |
| One handler/sink throws or PostHog is unavailable | Business outcome unchanged; other sinks attempted; bounded flush; no recursive logging |
| Same record formatted/exported twice | Same event ID and occurrence time in every projection |
| Missing required field, wrong type, invalid enum or reserved-field override | Invalid occurrence rejected safely; diagnostic counter observable outside the process |
| Concurrent/nested transactions, savepoint rollback, two commits in one request | Only the owning committed transaction emits its staged events, exactly once |
| Legacy/server/disabled ownership with old/new browsers and servers | No unintended collection gap in steady state; modern client obeys per-result owner; cached copies excluded from canonical reporting |
| Post-response export timeout or throw | Booking action does not wait for analytics; total lifecycle budget respected; no fallback conversion or dangling uncaught promise |
| Secret/PII and unknown-field fixtures | Disallowed values reach no sink; allowed delivery IDs survive |
| Existing mobile session and legacy logout requests | Compatible responses; no dependency on the new receiver/app |
| Healthy request, slow success, startup crash, CORS warning | Routine noise suppressed; slow signal and actionable/platform failures preserved |
| Existing Slack/environment configuration | Integration still functions using its established variable names |

Application tests and unchanged-platform failure preservation gate the application
release. Tests of new collector/Sanity ingestion filters gate only those filter
changes; absence of collector access does not silently waive them or block the
separate application release.

Run focused domain/contract tests and repository-required checks, then preview
integration tests with controlled fake providers. Run Personal's OpenAPI export
and consistency checks for the receiver removal. The earlier review's 14 unit
tests passed, but 11 API tests were blocked by absent database configuration;
rerun them in the configured harness. Prior PR CI counts do not establish these
new acceptance scenarios. Record actual evidence, not only a passing suite total.

## 8. Delivery order and release gates

1. **Scope correction:** split/defer Mobile #30 and Personal's new receiver;
   preserve old app API compatibility. Inventory deployed versions, dashboard
   definitions, existing collection settings and collector ownership. Remove
   unrelated changes from the observability PRs or document separate ownership.
2. **Shared foundation:** implement catalogs, logger wrappers, occurrence identity,
   per-sink isolation and shared fixtures in Personal/website.
3. **Personal remediation:** fix transaction timing, replay/no-op guards, domain
   semantics and API scope. Run configured tests and OpenAPI checks.
4. **Website remediation:** implement truthful outcomes, pseudonymous context
   handling, stable analytics names, SDK deduplication and lifecycle delivery.
   Prepare dashboard filters and the per-result browser/server ownership protocol
   in legacy mode, so browser conversion collection remains active while staging.
5. **Preview gate:** execute the full acceptance matrix across both services;
   verify no app update is needed and no preview telemetry pollutes production
   conversion reporting. Keep platform ingestion changes off.
6. **Application release:** deploy Personal first, then website operational
   changes. Verify correlated volunteer registration and backend/mobile
   compatibility. Keep existing analytics ownership until the cutover gate passes.
7. **Analytics cutover:** coordinate browser/server ownership and canonical query
   filters, record ownership intervals, and verify pseudonymous collection,
   old-client and duplicate scenarios against actual ingestion. If blocked,
   retain operational changes with legacy analytics ownership.
8. **Platform cleanup and observation:** enable only verified ingestion filters
   separately. Compare domain coverage, duplicates, export errors, latency and
   volume for seven days. Target zero routine success notices in the default
   domain view and zero duplicate canonical conversions; promise no reduction
   percentage before measurement.

Rollback analytics ownership and ingestion filtering independently. Set ownership
to `disabled` for an emergency analytics stop; updated clients must honor it even
when server export is unavailable. Cached clients cannot be remotely guaranteed
to stop by this marker alone; use the verified ingestion controls if a complete
stop is required. Restore `legacy` ownership only with the browser protocol and
reporting interval in place. Do not rewrite historical server-owned intervals
using the current flag. Test rollback with cached and current clients, and retain
existing opt-out behavior. Prefer a documented boundary gap over double counting.
Keep readable domain logs during an ingestion rollback where possible. Never
retry business writes to repair telemetry gaps.

## 9. Completion evidence and remaining external verification

The implementation is ready for release when the first-release acceptance matrix
passes in the configured harness, both shared fixture digests match, the old app
contract is verified, and ownership/rollback controls are exercised in preview.
The deployment is verified only after real ingestion, canonical reporting and
lifecycle delivery have been checked; the observation stage finishes after seven
days. PR CI success alone does not complete either later stage.

Keep a short release evidence record with PR head SHAs, configured test results,
fixture digest, preview checks, selected SDK/runtime delivery and deduplication
mechanisms, dashboard/query revision, ownership intervals, collector owner and
seven-day observations. Mark unknown deployed configuration as unverified, not
implemented. Dashboard access and collector ownership remain external facts to
verify during release; application work proceeds without inventing those facts.

## 10. Later mobile release: retained remediation backlog

Reopen this phase only after the Personal/website first release is stable.

- Define the dedicated receiver and app adapter together; authenticate where
  credentials exist, allow only approved coarse anonymous categories, mark claims
  `source=client`, and prohibit authoritative server events or trusted subject IDs.
- Enforce bounded payloads before expensive parsing, durable rate limits, strict
  per-event fields, and an explicit event-to-message/severity/outcome mapping.
  Preserve validated client occurrence time/ID; keep receipt time separate.
- Implement a serialized queue with at most 100 sanitized records/24 hours, drop
  oldest on overflow, allow one active flush, and remove acknowledged IDs without
  overwriting concurrent enqueues. Retry the same occurrence with bounded backoff
  and explicit online/app-lifecycle wakeups without blocking navigation.
- Start fallback only on actual degraded operation, not ordinary cached startup;
  recover once fresh data returns and coalesce repeated failures per episode.
- Wire collection preferences before enqueue/capture, clear or stop pending work
  appropriately on opt-out, and verify the supported React Native SDK behavior.
  Keep product analytics off by default with only approved UI events/properties.
- Test concurrency, offline recovery without new events, malformed responses,
  token persistence failures, logout, opt-out, anonymous abuse and old app versions.
  Regenerate OpenAPI and verify client compatibility before enabling the receiver.

Mobile fixes are explicitly deferred work, not prerequisites for the first
Personal/website logging release and not accepted as already complete.
