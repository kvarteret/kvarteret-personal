# Make email delivery durable and volunteer flows traceable

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `PLANS.md` in the repository root. It describes coordinated changes in this repository and in the adjacent `samfunnetibergen-reliable-form-submissions` website checkout. The plan is intentionally limited to durable email delivery and safe observability. It does not build a generic operations platform or implement the future “accept every open application” feature.

## Purpose / Big Picture

Volunteer lifecycle changes must succeed even when a related email cannot be delivered. Every volunteer-application lifecycle email migrated in this change—the application receipt, invitations, friend invitations, and the profile-completion email sent when a trial starts—must have a durable database record showing whether it is waiting, was accepted by the SMTP server, or failed. Transient failures must retry automatically, and an administrator must be able to inspect failures, correct an eligible volunteer email address, and retry delivery. Approval itself does not currently send an email on `develop`; this change preserves that behavior. Existing admin-onboarding and mobile-card email paths remain unchanged and outside this iteration.

A developer or administrator must also be able to follow a public volunteer registration from `samfunnetibergen.no`, through the Next.js proxy and the Personal API, into the Supabase-hosted Postgres record, and onward through profile completion, trial attendance, approval, and email delivery. The durable volunteer `registration_id` is the lifecycle correlation key. OpenTelemetry supplies a `trace_id` for each request, and Personal stores the initial trace ID with the registration so later requests can refer back to it. Booking submissions receive their own server trace and booking submission ID; this plan does not attempt to infer that a booking and a volunteer registration belong to the same person or browser.

After implementation, the behavior is visible in three places. The Personal admin UI shows durable email state and attempt history. PostHog shows sanitized application logs and request traces joined by `registration_id`, `origin_trace_id`, current `trace_id`, and `email_delivery_id`. The database remains the authoritative record if PostHog is unavailable or misses an event.

## Progress

- [x] (2026-08-11) Inspected the current approval, email, logging, PostHog, volunteer proxy, and booking submission paths.
- [x] (2026-08-11) Reduced the design from a generic operations and telemetry platform to two durable email tables plus lifecycle correlation on existing volunteer records and domain events.
- [x] (2026-08-11 11:59Z) Copied this canonical ExecPlan byte-for-byte into the dedicated `codex/durable-email-observability` Personal worktree, read the repository guidance and triggered skills, and confirmed the worktree started clean apart from this plan.
- [x] (2026-08-11 12:03Z) Established the starting state: Personal import contracts pass; full pytest cannot boot DB-backed app tests without `DATABASE_URL`; the unit portion passed before those failures; `ty` reports 108 existing diagnostics; asset build needs a prior `bun install`. Verified the website checkout is on `codex/reliable-form-submissions`, behind `origin/develop` by 12 commits, and unchanged except for the required untracked reliable-form ExecPlan.
- [x] (2026-08-11) Milestone 1 completed in both worktrees: allowlisted/redacted structured logging, server-side OTel logs and traces, W3C propagation, resource metadata, and sentinel-PII exporter tests are implemented. Live PostHog receipt remains a rollout check.
- [x] (2026-08-11) Milestone 2 completed: email-specific table definitions, additive migration, constraints, indexes, idempotency, and correlation columns passed upgrade, downgrade, and re-upgrade against a disposable Postgres database with the same Supabase schema stubs as CI.
- [x] (2026-08-11) Milestone 3 completed for volunteer-application email producers: they enqueue transactionally, best-effort immediate dispatch preserves response success, retry/lease/attempt behavior is implemented, and the protected once-per-five-minutes cron plus one-shot local dispatcher are wired.
- [x] (2026-08-11) Milestone 4 completed: admin list/detail/history, immutable successor retry, volunteer-only recipient correction, CSRF/authorization checks, and compact volunteer delivery status are implemented and covered by focused tests.
- [x] (2026-08-11) Milestone 5 completed in repository code: volunteer origin/current trace persistence, cross-service trace propagation, delivery correlation, booking submission correlation, Crescat propagation, and privacy assertions are implemented. Live PostHog searches remain a rollout check.
- [ ] Milestone 6 remains an external rollout milestone: production Vercel/PostHog configuration, captured-drain transformation validation, saved views, alerts, budgets, and the seven-day soak require deployment and project access and were intentionally not performed in this no-deploy worktree task.
- [x] (2026-08-11) Ran the highest-value repository validation: Personal unit/web `272 passed`; focused API/admin `8 passed`; disposable-Postgres lifecycle E2E `11 passed`; migration upgrade/downgrade/re-upgrade passed; Ruff, import contracts, public OpenAPI, frozen lockfile, and assets passed. Website focused tests `13 passed`; lint, Next type generation plus TypeScript, and production build passed. Personal `ty` still reports exactly the pre-existing baseline of 108 diagnostics.
- [x] (2026-08-11) Final root review changed the recovery cron to the agreed five-minute cadence and prevented unstructured log messages from entering OTLP; the expanded critical Personal suite passed `13 passed`, the website correlation suite passed `13 passed`, Ruff passed, and both worktrees passed `git diff --check`.
- [x] (2026-08-11) Reviewability refactor: renamed the coordinator to `EmailOutboxService`, extracted message preparation and outbox persistence/claim/attempt operations, restored admin-onboarding and mobile-card delivery to their exact pre-change implementation, removed the unused ciphertext/encryption dependency, and regenerated `uv.lock` with the repository's older lock format to avoid metadata churn. The focused outbox/observability suite passes `13 passed`.
- [x] (2026-08-11) Removed the volunteer application's legacy direct-send fallback. `VolunteerApplicationsService` and `VolunteerApplicationWorkflow` now require the outbox protocol, no volunteer-domain code imports the sender or applicant renderer, and an immediate dispatch failure leaves the committed application plus pending delivery intact. The final Personal suite passes `304 passed, 11 skipped`; the skips are the Postgres-only E2E tests already exercised before this refactor. Ruff, the public OpenAPI check, frozen lock synchronization, and all four import contracts pass.

## Surprises & Discoveries

- Observation: the documented Personal baseline commands assume database and frontend dependency setup that is not present in the clean worktree.
  Evidence: `uv run pytest` fails DB-backed tests with `DATABASE_URL is required for database-backed features`, `uv run ty check` reports 108 existing diagnostics, and `bun run build:assets` cannot resolve Tailwind before `bun install`; `uv run lint-imports` passes all four contracts.

- Observation: live PostHog/Vercel configuration and the seven-day production soak cannot be completed from a no-deploy worktree-only implementation.
  Evidence: the requested execution explicitly forbids deploys, while Milestone 6 requires production drains, saved views, alerts, and seven days of usage measurements. Repository-side exporters, configuration validation, and transformation fixtures remain implementable and testable.

- Observation: placing SQLAlchemy email table definitions under `app.infrastructure.email` breaks the repository's layer contract because infrastructure may not import the higher database layer.
  Evidence: `uv run lint-imports` reported `app.infrastructure.email.tables -> app.db.metadata`; moving only the definitions to `app/db/table_defs/email_delivery.py` restored the intended dependency direction without making the business model generic.

- Observation: running `uv run ruff format app ...` on the whole application reformatted unrelated pre-existing source and obscured the implementation diff.
  Evidence: `git diff --stat` temporarily showed changes in 52 tracked files, including unrelated groups, courses, Spotify, and volunteer modules. Those mechanical-only edits were restored from `HEAD` with explicit file-scoped `apply_patch` replacements; subsequent formatting is limited to newly added or directly modified files.

- Observation: `develop` moved the profile-completion email from approval to the start-trial transition and added an application-receipt email for public registrations while this branch was being prepared.
  Evidence: after rebasing onto `20260811_1200_volunteer_application_lifecycle`, `VolunteerApplicationWorkflow.start_trial` owns profile completion, public registration owns the receipt, and approval has no email side effect. The durable outbox must preserve those lifecycle semantics rather than reintroduce an approval email.

- Observation: the existing `domain_events` table already records volunteer lifecycle transitions by `subject_id`, including `prospect_registered` and `application_approved`.
  Evidence: `app/domain/volunteer_applications/tables.py`, `repository.py`, and `workflow.py` use the volunteer registration ID as the event subject.

- Observation: the public website already receives `registrationId` from Personal and returns it to its client. This is a durable, non-email lifecycle identifier and is a simpler correlation mechanism than a new browser journey identity.
  Evidence: `src/app/api/volunteer-prospects/route.ts` forwards `POST /api/v1/volunteer-prospects` and returns the backend response’s `registrationId`.

- Observation: current website failure telemetry deliberately includes the applicant’s email address.
  Evidence: `src/app/api/volunteer-prospects/route.ts` includes `email` in both backend-rejection and request-failure capture properties. This must be removed before expanding telemetry.

- Observation: Personal’s JSON logger writes application records to stdout. A Vercel log drain therefore sees the same application lines that direct OTLP log export would send.
  Evidence: `app/observability.py` installs a JSON formatter on the application logger and Vercel runtime drains include function stdout and stderr.

- Observation: admin onboarding prepares a Supabase recovery link before sending email, while mobile-card email contains a short-lived plaintext code whose hash is the only currently persisted authentication value.
  Evidence: the admin-account route generates the recovery action link inline, and `app/domain/mobile_card/service.py` commits the access-code hash before rendering and sending the plaintext code.

- Observation: a plain PostgreSQL container is not sufficient to exercise this repository's complete Alembic history because an older migration expects Supabase's `auth` schema and storage objects.
  Evidence: the first disposable migration run stopped at the pre-existing `20260318` migration with a missing `auth` schema. Recreating the CI Supabase role, function, and storage stubs allowed `upgrade head`, `downgrade -1`, and `upgrade head` to pass, including both email tables and both trace columns.

- Observation: the new administrative HTML routes initially changed the generated public OpenAPI document even though they are internal web UI, not supported API surface.
  Evidence: `scripts/export_openapi.py --check` showed only the new email-delivery form/page paths. Marking both email-delivery routers `include_in_schema=False` restored an exact contract match; the final contract and focused admin run passed eight tests.

- Observation: current `uv` versions rewrite old lock metadata even when the actual dependency change is small.
  Evidence: dependency resolution initially added lock revision/upload timestamps across the file. Regenerating with `uv 0.5.31` preserved the repository's compact lock format, leaving only the required OpenTelemetry dependency graph.

- Observation: migrating admin onboarding and mobile-card access codes in the same changeset created avoidable scope and made the outbox resemble a second email system.
  Evidence: those two migrations required Supabase link preparation, short-lived secret encryption, new runtime configuration, and parallel direct-send fallbacks. Restoring those domains to `HEAD` removed that complexity while preserving the volunteer-application durability requirement.

- Observation: sanitizing exception attributes is insufficient when legacy log calls interpolate arbitrary response bodies or other values into their message text.
  Evidence: existing unstructured log call sites include external response text, and the website's Crescat client previously appended its response body to a captured failure. The final Personal formatter now exports `log.message` for unstructured records and the stable event name for structured records; the Crescat error is status-only; regression tests prove that direct identifiers do not enter the reviewed telemetry paths.

## Decision Log

- Decision: build only `email_deliveries` and `email_delivery_attempts` as new durable concepts.
  Rationale: these tables directly answer whether mail succeeded, failed, or can be retried. Existing volunteer records and `domain_events` already describe the business lifecycle, so `operation_runs`, `operation_items`, stale-operation reconciliation, and a telemetry outbox are unnecessary in this iteration.
  Date/Author: 2026-08-11 / Codex

- Decision: treat SMTP acceptance as delivery success and document at-least-once behavior.
  Rationale: the SMTP sender can establish that the upstream server accepted a message, but cannot prove inbox placement. A network failure after remote acceptance can lead to one duplicate retry. This is preferable to silently losing the message.
  Date/Author: 2026-08-11 / Codex

- Decision: use five total automatic attempts: initial, then after 1 minute, 5 minutes, 30 minutes, and 2 hours.
  Rationale: this removes the earlier contradiction between five and six attempts and avoids an immediate retry against a service that has just failed. An administrator can create a new manual retry after the automatic schedule is exhausted.
  Date/Author: 2026-08-11 / Codex

- Decision: use a five-minute lease, a batch size of ten, and a 20-second timeout per external email preparation or SMTP call.
  Rationale: the lease remains longer than the worst expected batch duration, while a once-per-five-minutes cron can safely skip rows owned by a preceding invocation. Lease fields are claim metadata, not delivery status.
  Date/Author: 2026-08-11 / Codex

- Decision: reserve an attempt row before preparation or SMTP work and keep one simple `stage` field.
  Rationale: failures can occur while loading application state, rendering, or contacting SMTP. A row left `started` after its lease expires truthfully indicates an interrupted attempt without requiring a general workflow engine.
  Date/Author: 2026-08-11 / Codex

- Decision: make PostHog best effort and keep Postgres authoritative.
  Rationale: durable email rows already preserve the success and failure data. Retrying analytics delivery would add infrastructure without improving email reliability. Missing PostHog telemetry can be reconstructed from Postgres during an incident.
  Date/Author: 2026-08-11 / Codex

- Decision: start traces at the Next.js server boundary and do not add browser OpenTelemetry or a cross-request browser journey ID.
  Rationale: browser tracing is not needed to follow a submitted request. The website explicitly propagates standard W3C trace headers to Personal and Crescat, while durable domain IDs correlate later work.
  Date/Author: 2026-08-11 / Codex

- Decision: use `registration_id` plus a stored `origin_trace_id` to correlate the volunteer lifecycle.
  Rationale: `registration_id` is created by Personal, persisted in Supabase Postgres, returned to the website, and reused by all later volunteer actions. Storing the inbound creation trace alongside it lets later logs and traces link to the initial request without identifying the person by email.
  Date/Author: 2026-08-11 / Codex

- Decision: classify internal IDs, trace IDs, and activity-linked records as pseudonymous rather than anonymous.
  Rationale: these values exclude direct identifiers but can still be related to a person through the authoritative system. Documentation and PostHog governance must use accurate data-classification language.
  Date/Author: 2026-08-11 / Codex

- Decision: use allowlisted telemetry fields and defense-in-depth redaction.
  Rationale: recursive detection cannot reliably identify names, addresses, tokens, or every future form field. Logging helpers must accept only known scalar fields; key and pattern redaction remains a fallback rather than the primary privacy boundary.
  Date/Author: 2026-08-11 / Codex

- Decision: send application logs only through OTLP and use the Vercel drain only for request, platform, and build metadata.
  Rationale: Vercel drains include function stdout and stderr. Dropping those records in a PostHog pre-ingestion transformation prevents duplicate application logs and reduces the PII surface.
  Date/Author: 2026-08-11 / Codex

- Decision: scope the durable outbox to volunteer-application lifecycle email in this iteration.
  Rationale: this is the flow that must remain successful when acceptance email delivery fails and the flow that needs later bulk-accept evidence. Admin onboarding and mobile-card access codes keep using the existing sender unchanged; migrating them can be evaluated independently if they later need durability.
  Date/Author: 2026-08-11 / Codex

- Decision: keep the email tables specific, but factor the durable coordinator into an `EmailOutboxService` in `app/email_outbox_service.py`, `EmailOutboxRepository`, and `EmailMessagePreparer` while reusing `EmailSenderProtocol` as the sole transport.
  Rationale: the names and dependency direction make the boundary explicit. The outbox persists and dispatches volunteer-application work; it does not replace SMTP or console delivery, and unrelated email domains do not depend on it.
  Date/Author: 2026-08-11 / Codex

- Decision: require the outbox in the volunteer application service and workflow instead of retaining a direct-send fallback.
  Rationale: optional outbox wiring created two possible orchestration paths and allowed a deployment misconfiguration to silently bypass durability. Volunteer actions now have one path: persist business state and delivery intent atomically, commit, then ask the outbox to dispatch through the existing sender.
  Date/Author: 2026-08-11 / Codex

- Decision: retain the dispatch cron in addition to immediate best-effort dispatch.
  Rationale: immediate dispatch provides low latency but cannot recover from an SMTP outage, process termination, or a request that commits immediately before the function stops. The cron is the recovery driver for durable pending rows; leases and idempotency make overlapping invocations safe. Without it, the outbox would require manual dispatch and would not provide automatic delivery guarantees.
  Date/Author: 2026-08-11 / Codex

- Decision: export only stable event names and allowlisted fields, never free-form Python log message text, through OTLP.
  Rationale: pattern matching cannot reliably remove names, phone numbers, addresses, or arbitrary upstream response bodies. Legacy unstructured records retain logger, severity, trace context, and exception class, while useful operational detail must be expressed through a named structured event.
  Date/Author: 2026-08-11 / Codex

## Outcomes & Retrospective

The reviewability refactor is complete without commits, pushes, or deployments. Personal now has a volunteer-application email outbox with attempt evidence and automatic recovery; the existing SMTP/console sender remains the sole transport. Volunteer-domain code has no direct-send fallback. Admin-onboarding and mobile-card email changes were removed from this changeset. Administrators can inspect and safely recover volunteer-application failures. Volunteer and booking paths emit and propagate pseudonymous correlation IDs through allowlisted telemetry, with direct-identifier sentinel tests on both sides.

The implementation deliberately did not introduce generic operation tables. Existing volunteer records and domain events already provide the business lifecycle; the two email-specific tables model only the reliability boundary that needs durable state. It also deliberately keeps the cron: request-time dispatch is an optimization, while scheduled dispatch is what recovers committed rows after transient failures or function termination.

Verification completed locally: Personal unit/web `272 passed` with 12 deprecation warnings; focused public-contract/admin tests `8 passed`; disposable-Postgres volunteer lifecycle E2E `11 passed`; Alembic upgrade/downgrade/re-upgrade passed with CI-equivalent Supabase stubs; Ruff, four import contracts, public OpenAPI export, frozen lock synchronization, and the asset build passed. Personal `ty` remains nonzero with exactly its baseline 108 diagnostics, so this change introduced no new type diagnostics. Website focused telemetry/proxy/booking tests `13 passed`; lint covered 377 files; `next typegen` plus `tsc --noEmit` passed; and the Next.js production build passed with all 76 static routes generated. `npm install` reported 30 existing dependency-audit findings (22 moderate, 8 high), which were outside this scoped change.

Production success rates, unresolved delivery counts, duplicate observations, PostHog ingestion volume, transformation behavior, alerts, and sampling budgets cannot be measured until deployment. Those are explicitly retained as Milestone 6 rollout work, including the seven-day soak and direct inspection of live PostHog/Vercel records. No real messages were sent during local verification.

## Context and Orientation

`kvarteret-personal` is a FastAPI application deployed as stateless Vercel Functions. “Stateless” means a function invocation cannot depend on memory or local files surviving after the response. Durable retry state must therefore live in the Supabase-hosted Postgres database. `app/main.py` constructs request middleware, `app/observability.py` formats current JSON logs, and `app/runtime.py` wires concrete infrastructure into domain services.

Email infrastructure is under `app/infrastructure/email/`. `smtp.py` sends production SMTP messages, `console.py` writes development messages, and the three template modules render applicant, admin-account, and mobile-card messages. The durable volunteer-application path wraps that existing transport; admin-account and mobile-card calls remain on their existing direct paths and are not changed here.

Volunteer applications are represented by rows owned by `app/domain/volunteer_applications/tables.py`. The primary row is `volunteer_application_invites`; its integer `id` is called `registration_id` in domain code and `application_id` in some web route parameters. Those names refer to the same lifecycle identifier. `domain_events` stores lifecycle transitions with that identifier as `subject_id`. Approval routes are in `app/web/routes/volunteer_applications/actions.py`.

The sibling `samfunnetibergen` website is a Next.js application. `instrumentation.ts` currently initializes PostHog error capture and an OTLP log exporter. `instrumentation-client.ts` initializes `posthog-js`. The public volunteer route, `src/app/api/volunteer-prospects/route.ts`, validates a request and forwards it to Personal. Room booking is handled by `src/features/booking/actions/submit-room-booking.ts`, which calls Crescat through `src/lib/integrations/crescat/client.ts` and receives a Crescat event identifier on success.

OpenTelemetry, abbreviated OTel, is a vendor-neutral format for logs and traces. A trace is the record of one request as it crosses services; each service contributes timed spans. W3C `traceparent` and `tracestate` headers carry this context over HTTP. A trace does not span the days between public registration and later approval. That longer lifecycle is joined by the persisted `registration_id` and `origin_trace_id` properties.

An outbox is a database table of work that must happen after a business transaction. Creating an email row in the same transaction as the lifecycle action that produces it guarantees that either both the action and queued email commit, or neither commits. A dispatcher is ordinary request-driven code that claims due rows and sends them. It is invoked once immediately after commit for low latency and again by a Vercel Cron for recovery; it is not a continuously running process.

The website worktree contains an untracked ExecPlan at `.agents/execplans/014-reliable-form-validation-and-submission-feedback.md`. Its volunteer milestone also removes raw applicant email from PostHog. Because that file is not committed, this plan is self-contained and does not depend on it. When implementing in that worktree, preserve the existing plan and coordinate overlapping edits instead of replacing them.

## Plan of Work

### Milestone 1: establish safe logs and server traces

Start in Personal. Refactor `app/observability.py` so application code emits named events through helpers that accept an allowlist of scalar properties. The common allowlist is `event`, `service`, `environment`, `request_id`, `trace_id`, `span_id`, `registration_id`, `origin_trace_id`, `volunteer_id`, `email_delivery_id`, `template_key`, `status`, `outcome`, `failure_stage`, `error_category`, `smtp_status_class`, `attempt_no`, `duration_ms`, `http_method`, `route_template`, and numeric counts. Add an explicit extension mechanism where a new named event declares its extra low-cardinality fields in code and tests them. Do not pass domain objects, request bodies, HTTP headers, recipient addresses, rendered messages, raw exception messages, or URLs into these helpers.

Keep a final redaction formatter that removes forbidden keys, query strings, email-like text, authorization values, cookies, and token-bearing path segments if a caller violates the allowlist. Replace current production fields `client_ip` and `username` with internal account IDs only where authorization diagnostics require them. Normalize `/apply/<token>` and other dynamic paths to their FastAPI route template before export. Change `SmtpDeliveryError` to carry a stable category and optional SMTP status code without embedding the recipient or raw server response in its string representation.

Add the Python OTel API, SDK, OTLP HTTP exporter, FastAPI instrumentation, and `httpx` instrumentation as runtime dependencies in `pyproject.toml`. Initialize them from a new small module called by `app/main.py`. Export logs to `https://eu.i.posthog.com/i/v1/logs` and traces to `https://eu.i.posthog.com/i/v1/traces`. Configure both exporters with `Authorization: Bearer ${POSTHOG_PROJECT_TOKEN}`. Attach `service.name=kvarteret-personal`, deployment environment, Vercel deployment ID, release/commit, and region as resource attributes. If telemetry is disabled or export fails, requests continue and a sanitized local warning is written.

In the website, keep `instrumentation.ts` as the framework entry point and conditionally load a new `instrumentation.node.ts` only when `process.env.NEXT_RUNTIME === "nodejs"`. Move the current OTLP log initialization into the Node module, change its endpoint from `/otlp/v1/logs` to `/i/v1/logs`, add the Node trace SDK and OTLP trace exporter, and use the same Bearer project-token header. Set `service.name=samfunnetibergen`. Preserve `onRequestError`, but ensure its properties follow the same no-direct-identifier rule.

This milestone is complete when a local request in each app creates a trace with a server span, structured logs contain its trace and span IDs, deliberately supplied sentinel emails and tokens do not appear in captured records, and disabling the exporter does not change the HTTP response.

### Milestone 2: create the minimal durable email model

Add table definitions in a new infrastructure-owned email-delivery module and expose them through `app/db/tables.py`. Create one Alembic migration from the current migration head at implementation time.

`email_deliveries` has a UUID primary key, `template_key`, integer `template_version`, `recipient_email`, `business_type`, `business_id`, optional `source_domain_event_id`, a caller-supplied unique `idempotency_key`, `status`, `automatic_attempt_count`, `next_attempt_at`, `lease_owner`, `lease_until`, sanitized `last_error_category`, optional `encrypted_context`, `enqueued_trace_id`, `registration_id`, optional `supersedes_delivery_id`, `created_at`, `updated_at`, and `sent_at`. Restrict status to `pending`, `sent`, `failed`, `expired`, or `cancelled`. A lease never changes status; it only makes a due row temporarily unavailable to other dispatchers.

`email_delivery_attempts` has a generated integer key, delivery UUID, monotonically increasing `attempt_no`, `stage`, `outcome`, sanitized `error_category`, optional SMTP numeric code and status class, `duration_ms`, `started_at`, and `finished_at`. Restrict stage to `prepare`, `render`, or `smtp`, and outcome to `started`, `succeeded`, `retryable_failure`, `permanent_failure`, or `interrupted`. Enforce uniqueness on `(delivery_id, attempt_no)`.

The attempt row is inserted with `outcome=started` before preparation begins. The dispatcher updates `stage` as it moves forward and finalizes the outcome afterward. When a delivery is reclaimed after an expired lease, any older `started` attempt is first marked `interrupted`; if its last stage was `smtp`, the UI explains that SMTP may have accepted the message before the worker disappeared. The delivery is retried because the system promises at-least-once, not exactly-once, behavior.

Add nullable `origin_trace_id` to `volunteer_application_invites` and nullable `trace_id` to `domain_events`. The public registration transaction writes the active inbound trace ID to both the new invite row and its `prospect_registered` event. Later lifecycle events store their own request trace ID. Existing rows remain valid with null correlation values.

Keep email contents minimal. Store `template_key`, a code-owned `template_version`, and the business reference rather than rendered HTML or invitation tokens. A versioned renderer must remain available while pending rows reference it. Read explicitly mutable display fields from current volunteer-application state. Application invitation tokens remain in their existing authoritative tables and are not copied into the outbox.

This milestone is complete when migration upgrade and downgrade tests pass, existing data remains readable, uniqueness prevents duplicate logical enqueue, and database constraints reject invalid status, stage, and outcome values.

### Milestone 3: enqueue and dispatch every current email

Define a small domain-facing outbox protocol and wire `EmailOutboxService` through `app/runtime.py`. Keep persistence/claim/attempt SQL in `EmailOutboxRepository`, template-specific reads/rendering in `EmailMessagePreparer`, and the existing `EmailSenderProtocol` behind the dispatcher. The enqueue call accepts a template key/version, business reference, recipient, idempotency key, optional registration and domain-event IDs, and current trace ID.

Change each volunteer-application workflow so the business mutation, its `domain_events` row where applicable, and `email_deliveries` insert share one transaction. Derive the idempotency key from the committed domain-event occurrence plus template and recipient role; a later explicit resend creates a new domain event and therefore a new valid delivery. Do not derive idempotency solely from template and recipient because that would suppress legitimate resends.

After commit, call the dispatcher once as a best effort for actions that queued volunteer email. Failure at this point must not change the successful registration, invitation, resend, or trial-start response. The durable row remains pending or failed and the user-facing response says the business action succeeded while delivery is queued or needs attention, as appropriate for the existing page. The cron processes each row independently, so one send failure cannot prevent later deliveries.

The dispatcher claims no more than ten due deliveries with `SELECT ... FOR UPDATE SKIP LOCKED`, assigns a random lease owner, and sets `lease_until` five minutes ahead. Each external preparation or SMTP operation uses a 20-second timeout. Automatic attempts occur at initial dispatch, then 1 minute, 5 minutes, 30 minutes, and 2 hours after the preceding retryable failure. SMTP 4xx, timeouts, and connection failures are retryable. Invalid-recipient conditions and SMTP 5xx are permanent. Configuration and decryption errors are permanent and high severity. Supabase onboarding-link preparation failures are classified by their HTTP status or exception category before SMTP is attempted. After five failed automatic attempts, mark the delivery failed.

Add `GET /internal/cron/dispatch-email-deliveries`, authenticated by exact `Authorization: Bearer ${CRON_SECRET}`. Configure `vercel.json` to call it every five minutes and give the function a duration compatible with the ten-message, 20-second bound. A five-minute Vercel Cron requires a deployment plan that supports sub-daily schedules; production rollout must not proceed on a daily-only plan. The endpoint is safe under overlapping calls because leases and row locks prevent concurrent claims.

Local development uses the existing console sender behind the same dispatcher. Provide a small CLI or test helper that dispatches due rows once, so developers do not need Vercel Cron locally.

This milestone is complete when SMTP success records an attempt and marks the row sent; a simulated 451 schedules the documented retries; a simulated 550 marks failure; a crashed/expired claim becomes an interrupted attempt and is reclaimed; and two simultaneous dispatcher calls never claim the same delivery.

### Milestone 4: make failures visible and retryable

Add an admin-only email-deliveries page using existing FastAPI authorization, Jinja, HTMX, and CSRF conventions. Default the list to unresolved failures, with optional filters for pending, sent, expired, template, and date. Show delivery ID, template, masked recipient, business link, registration ID where present, status, attempt count, last sanitized error, next attempt, timestamps, and attempt history. Show `enqueued_trace_id` as a copyable value or link to the configured PostHog project. Do not render raw SMTP responses.

Add a POST action for manual retry. It must not mutate a terminal delivery. Instead, it creates a successor delivery with `supersedes_delivery_id`, a new action-occurrence idempotency key, and a fresh automatic-attempt budget. The predecessor remains as immutable evidence. Reject retry of an expired mobile-card code and direct the administrator or user to request a new code.

Add recipient correction for volunteer application templates. Validate the replacement using the existing email normalization and duplicate checks, update the authoritative invite/submission/group-member or promoted-volunteer email fields required by that application in one Postgres transaction, and create a successor delivery addressed to the corrected value. Record the actor and delivery IDs through the existing `admin.activity` event and sanitized log; do not send either old or new address to PostHog.

Add a compact delivery status and link to the relevant volunteer application page, so a manager can see “sent”, “retrying”, or “failed” for that application’s lifecycle emails. The global delivery page remains admin-only because it spans groups and account types.

This milestone is complete when an administrator can force a safe permanent failure, find it without searching raw Vercel logs, inspect its attempts, retry it, and observe a successor reach sent status. A volunteer address correction must update the domain record and deliver the successor; unauthorized and CSRF-invalid requests must fail.

### Milestone 5: correlate public submissions and later lifecycle actions

In the website volunteer proxy, start or use the active Next.js server span. Before calling Personal, explicitly inject the active W3C `traceparent` and `tracestate` into the outbound headers using the OTel propagation API; do not rely on undocumented browser PostHog behavior. Remove raw applicant email from every PostHog capture. On a successful response, add the returned `registrationId` and current trace ID to the existing `volunteer_application_submitted` event and to a sanitized structured log.

In Personal’s public prospect route and workflow, read the active server trace ID from OTel context, persist it as `origin_trace_id` on the created registration, and store it on the `prospect_registered` domain event. Return `registrationId` exactly as today. Subsequent profile, trial, approval, resend, and deletion requests attach the current trace ID, `registration_id`, and stored `origin_trace_id` to their spans and allowlisted logs. Email rows created by registration, invitation, resend, or trial-start actions additionally carry `email_delivery_id` and their enqueue trace ID. Cron delivery starts a normal new trace; its logs and spans include these durable IDs as attributes. Do not create a synthetic parent-child relationship across hours or days.

The resulting query path is:

    website volunteer request trace_id=T1
      -> Personal POST span trace_id=T1
      -> volunteer_application_invites.id=R, origin_trace_id=T1
      -> domain_events subject_id=R
      -> later approval trace_id=T2, registration_id=R, origin_trace_id=T1
      -> email delivery D, registration_id=R, enqueued_trace_id=T2
      -> cron trace_id=T3, email_delivery_id=D, registration_id=R

For room booking, create a random `booking_submission_id` at the start of the server action, add it to the action span, structured logs, and existing success/failure PostHog events, and add the returned Crescat event ID after acceptance. Instrument and propagate standard trace context on the Crescat HTTP request, while treating Crescat as an external leaf that may ignore the headers. This lets operators correlate one booking request and its upstream result; it does not join bookings to volunteer registrations or identify a browser across separate requests.

Add tests that capture the headers sent by the website, assert Personal persists the same 32-character lowercase trace ID, and assert later lifecycle logs contain both the new trace and original trace. Use invented IDs and sentinel PII, then assert the PII is absent from telemetry.

This milestone is complete when a PostHog search for `registration_id=R` shows the website submission, initial Personal request, later approval, and email outcome, while a search for `booking_submission_id=B` shows the booking action and Crescat result.

### Milestone 6: configure PostHog and the Vercel drains

Use the existing EU PostHog project. Direct OTLP logs and traces authenticate with the project token and arrive under the two service names. Configure Vercel production drains for both projects to send runtime/request and build metadata. Start with production only and exclude static-request traffic.

Before storing drain events, add and test a PostHog transformation against a captured Vercel fixture. Drop function stdout and stderr records because application logs already arrive through OTLP. Drop query strings, bodies, headers, cookies, IP addresses, raw URLs with tokens, and unknown properties. Retain only Vercel project, deployment, environment, source/type, level, request method, normalized route, status, duration, platform request ID, trace ID, and span ID. If the live Vercel schema uses different discriminator names than the fixture, update the transformation and record the discovery here before enabling production ingestion.

Create PostHog saved log views for permanent delivery failures, retryable failures, each service, `registration_id`, `email_delivery_id`, and `booking_submission_id`. Create trace views for cross-service volunteer requests and booking requests. Create PostHog-native alerts for any permanent delivery failure, any dispatcher-level failure, and an increase in failed approval requests. These are convenience signals; the Personal admin page and database remain authoritative.

Run a seven-day production soak at 100% OTel trace/log export and 100% eligible Vercel drain sampling. Record daily ingestion volume. If projected PostHog Logs usage exceeds 8 GB per month, or Vercel drain transfer cost exceeds the agreed project budget, keep errors and business delivery logs at 100% but reduce successful request/platform sampling. Do not sample durable failure rows or remove the admin failure view. Record the chosen post-soak sampling values in this Decision Log.

This milestone is complete when application records appear once through OTLP, Vercel platform/request records appear through the drain, a synthetic trace joins website and Personal, alert tests fire in PostHog, and a sampled-record inspection finds no direct identifiers.

## Concrete Steps

Work on a dedicated `codex/` branch in each repository. Before every milestone, run `git status --short` and preserve unrelated changes. In Personal, the existing modifications to `app/templates/pages/auth/login.html` and `mise.toml` are user-owned and outside this plan. In the website worktree, preserve the untracked reliable-form ExecPlan and reconcile overlapping volunteer-route edits manually.

From Personal, install dependencies and establish the baseline:

    cd "$(git rev-parse --show-toplevel)"
    uv sync --all-groups
    uv run alembic heads
    uv run pytest
    uv run ruff check .
    uv run ty check
    uv run lint-imports

After creating the migration, inspect that it revises the single current head, then exercise it:

    uv run alembic upgrade head
    uv run alembic downgrade -1
    uv run alembic upgrade head

The upgrade should create both email tables and add the nullable correlation columns. The downgrade should remove only those additions. Never run downgrade against production data.

After each Personal milestone, run focused tests for the touched services and then the full checks:

    uv run pytest tests/unit tests/web
    uv run pytest tests/e2e/test_volunteer_lifecycle.py
    uv run pytest
    uv run ruff check .
    uv run ty check
    uv run lint-imports
    bun run build:assets

From the website worktree, install dependencies and establish its baseline:

    cd ../samfunnetibergen-reliable-form-submissions
    npm install
    npm test
    npm run lint
    npm run build

After the tracing changes, run at minimum the volunteer route, booking action, Crescat client, instrumentation, and PostHog tests, followed by the full commands above. Use the actual existing test filenames discovered with `rg --files src | rg '(volunteer-prospects|submit-room-booking|crescat|instrumentation|posthog).*test'`; do not invent a path when adding to the command transcript.

For local end-to-end verification, configure PostHog export off, run the website and Personal against a disposable database and console email sender, submit a volunteer through the website, complete or approve it in Personal, and invoke the one-shot dispatcher. Record the generated registration ID, request trace IDs, delivery ID, database statuses, and console outbox filename in `Artifacts and Notes`. Use fake SMTP adapters for failure paths; do not send real messages.

Before production rollout, configure these environment variables in the appropriate Vercel projects and pull them into an ignored local file only when needed:

    POSTHOG_OBSERVABILITY_ENABLED=true
    POSTHOG_PROJECT_TOKEN=<EU project token>
    POSTHOG_HOST=https://eu.i.posthog.com
    OTEL_SERVICE_NAME=<repository service name>
    CRON_SECRET=<random bearer secret, Personal only>

Production startup must reject an enabled email dispatcher without its cron secret. Telemetry configuration failure must not prevent startup because PostHog is non-authoritative.

## Validation and Acceptance

The primary acceptance scenario begins with a public volunteer submission. Submit safe synthetic data to the website in a non-production or explicitly approved test environment. The website returns HTTP 201 with a `registrationId`. Personal’s Supabase Postgres database contains that registration with `origin_trace_id`. The `prospect_registered` domain event has the same subject and trace ID. PostHog shows one trace spanning the Next.js route and Personal endpoint, and searching by the registration ID finds sanitized records without the applicant’s name, email, phone, or form text.

Continue the same synthetic registration through trial start, profile completion, and individual approval. Make the SMTP adapter return a retryable failure for the trial-start profile-completion email. The trial state still commits, the database contains one delivery linked to the registration and one failed attempt, and the application can later be approved independently. PostHog shows the later lifecycle traces with both `registration_id` and `origin_trace_id`, making the initial trace discoverable.

Advance time or invoke the dispatcher with a test clock. Verify attempts occur at the initial time and then at 1 minute, 5 minutes, 30 minutes, and 2 hours after retryable failures. After a later success, the delivery is `sent` and `sent_at` is populated. After five retryable failures or one permanent failure, it is `failed` and appears in the admin page. The page’s attempt stages and sanitized errors agree with the database.

For multiple queued invitations or trial-start messages, inject a failure for one recipient and success for the others. Every intended email has its own durable row, and the failing recipient does not stop later rows from dispatching.

For manual recovery, select a failed volunteer delivery and retry it. The original remains failed, a successor row references it, and the successor can be sent. Correct the address using synthetic values and verify both the authoritative application data and successor delivery change in one transaction.

For concurrency, pause one fake SMTP call after its row is leased and invoke the cron endpoint again. The second request must not claim that row. Advance beyond the five-minute lease, simulate the original worker disappearing, and verify the next invocation marks the old started attempt interrupted before retrying. No test should claim exactly-once delivery.

For PostHog privacy, use sentinel values resembling a name, email, phone, bearer token, application token, cookie, and free-text form answer. Capture success and each failure stage, inspect the exporter payload and Vercel transformation output, and assert none of the sentinels appear. Internal IDs and trace-linked activity are permitted but documented as pseudonymous.

For duplicate prevention, send one structured application log to stdout and OTLP. The PostHog transformation must discard its Vercel stdout copy, leaving exactly one application-log record. A Vercel request or invocation metadata record for the same request must remain available.

For booking correlation, make one fake Crescat submission. PostHog must show the Next.js server trace, `booking_submission_id`, client call span, and fake Crescat event ID. No applicant or booking contact value may appear.

All focused tests and both repositories’ full test, lint, type, import-boundary, asset, and production-build commands must pass, or any unrelated baseline failure must be recorded here with proof that the new focused checks pass.

## Idempotence and Recovery

The migration is additive and nullable for existing volunteer data. Run it once per environment through the normal Alembic deployment path. Re-running `upgrade head` is safe. Test downgrade only on disposable databases because removing the tables discards delivery history.

Enqueue is idempotent through a unique logical action key. A duplicate request for the same committed domain-event occurrence returns the existing delivery rather than inserting another. A deliberate resend or manual retry creates a new action occurrence and successor delivery, so it is not mistaken for a duplicate.

Dispatch is recoverable because row locks serialize claims and leases expire. A deployment or function crash leaves the delivery pending. The next cron invocation records an interrupted prior attempt and retries. If PostHog is unavailable, only telemetry is lost; the database and admin view still show the complete delivery history.

The SMTP boundary is at-least-once. If the upstream accepts a message but the function dies before recording success, retry can send a duplicate. The UI must label an interrupted SMTP-stage attempt as potentially delivered and require an administrator to consider that before manual retry. Do not delete or rewrite the original attempt.

Disable automatic dispatch with an environment flag if SMTP or cron behavior is unsafe during rollout. This leaves rows queued. Re-enable it after correcting configuration; do not purge or bulk-update pending rows. Manual dispatch uses the same claim path and is safe to repeat.

## Artifacts and Notes

Record concise evidence as implementation proceeds. Useful examples are the migration head before and after, one redacted OTLP payload, one `traceparent` captured by the Personal test client, one successful and one failed delivery row with attempts, the PostHog query used to find a registration lifecycle, and the Vercel transformation fixture proving stdout removal.

The intended correlation shape is:

    initial public request: trace_id=T1, registration_id=R
    later application action: trace_id=T2, origin_trace_id=T1, registration_id=R
    queued delivery: email_delivery_id=D, enqueued_trace_id=T2, registration_id=R
    cron attempt: trace_id=T3, email_delivery_id=D, registration_id=R

The intended delivery state change is:

    business transaction commits -> pending delivery
    dispatcher claims lease -> started attempt
    SMTP accepts -> successful attempt + sent delivery
    retryable failure -> failed attempt + pending delivery with next_attempt_at
    permanent/exhausted failure -> failed attempt + failed delivery
    administrator retries -> immutable failed delivery + new pending successor

Do not paste live emails, names, tokens, raw SMTP messages, or request bodies into this section. Replace identifiers with `R`, `D`, `T1`, and similarly invented values.

## Interfaces and Dependencies

In Personal, add runtime dependencies for the OpenTelemetry API and SDK, OTLP HTTP exporters, FastAPI instrumentation, and `httpx` instrumentation. Use the PostHog EU OTLP endpoints with a Bearer project-token header.

Define the domain-facing enqueue shape in a shared, dependency-safe module:

    @dataclass(frozen=True)
    class EmailDeliveryRequest:
        template_key: str
        template_version: int
        recipient_email: str
        business_type: str
        business_id: str
        idempotency_key: str
        registration_id: int | None = None
        source_domain_event_id: int | None = None
        encrypted_context: bytes | None = None

    class EmailDeliveryOutboxProtocol(Protocol):
        async def enqueue(self, request: EmailDeliveryRequest) -> UUID: ...

The concrete service must expose:

    async def dispatch_due(*, batch_size: int = 10) -> DispatchSummary: ...
    async def retry_failed(delivery_id: UUID, *, actor_user_account_id: int) -> UUID: ...
    async def correct_volunteer_recipient(
        delivery_id: UUID,
        *,
        recipient_email: str,
        actor_user_account_id: int,
    ) -> UUID: ...

`DispatchSummary` contains only counts and delivery IDs; it contains no recipient data. SMTP failure classification returns stable `error_category`, retryability, and optional numeric status without a raw response string.

The protected cron interface is:

    GET /internal/cron/dispatch-email-deliveries
    Authorization: Bearer <CRON_SECRET>

It returns HTTP 200 with a sanitized JSON count summary when enabled, HTTP 200 with `{"disabled": true}` when deliberately disabled, and HTTP 401 for a missing or invalid secret. It must never return recipient addresses or exception text.

The website adds the OTel API, Node SDK, semantic-convention resource helpers, and OTLP HTTP trace exporter compatible with its installed Next.js version. `instrumentation.ts` imports Node initialization conditionally. The volunteer proxy explicitly injects W3C headers on its Personal fetch. Public response shapes remain unchanged: successful volunteer registration still returns `{ "registrationId": <id> }`, and booking actions retain their existing `Result<number>` contract.

PostHog event properties added by this plan are allowlisted: `service`, `environment`, `trace_id`, `registration_id`, `origin_trace_id`, `email_delivery_id`, `booking_submission_id`, `crescat_event_id`, `template_key`, `outcome`, `failure_stage`, `error_category`, `attempt_no`, `duration_ms`, and low-cardinality existing group/feature flags. Set person-profile processing off for server operational events. Direct identifiers and arbitrary objects are forbidden.

Revision note (2026-08-11): Replaced the earlier broad design after two architecture reviews and user clarification. This version removes operation runs/items, durable telemetry, browser journey identity, synthetic cross-request traces, generic sagas, and future bulk-approval abstractions. It retains durable email attempts, safe retry/correction, sanitized PostHog logs and traces, and adds the explicit requirement to correlate the website’s initial volunteer submission with the Supabase registration and all later volunteer lifecycle actions through `registration_id` and `origin_trace_id`. After implementation, the recovery cron cadence was changed from every minute to every five minutes to match the final user discussion while retaining automatic recovery.

Revision note (2026-08-11 11:59Z): Began implementation in the dedicated clean Personal worktree and recorded the verified starting state so another contributor can resume from this living plan alone.

Revision note (2026-08-11 12:03Z): Recorded reproducible baseline limitations and the no-deploy boundary for Milestone 6; these facts affect validation and rollout but do not weaken the durable outbox or telemetry privacy requirements.

Revision note (2026-08-11 12:34Z): Updated Milestones 2 and 3 with the implemented vertical slice, focused-test evidence (`15 passed`), and the dependency-safe placement decision discovered through import-linter.

Revision note (2026-08-11 12:43Z): Recorded and cleaned up accidental repository-wide formatter churn so the remaining diff is scoped to the durable-email and observability implementation.

Revision note (2026-08-11): Refactored the oversized delivery coordinator into explicit outbox, repository, and preparation responsibilities; renamed it to avoid implying a second transport; restricted durability to volunteer-application mail; restored admin/mobile email paths; removed encryption scope; and normalized `uv.lock` with the repository's compact format.

Revision note (2026-08-11): Removed the final volunteer direct-send fallback, made outbox wiring mandatory at both service and workflow boundaries, removed obsolete import-layer exceptions, and replaced rendered-email domain assertions with enqueue assertions.

Revision note (2026-08-11): Recorded final refactor verification: `304 passed, 11 skipped`, with the skipped set requiring `E2E_DATABASE_URL`; affected volunteer web/OpenAPI checks, Ruff, import contracts, frozen lock synchronization, and diff checks all pass.

Revision note (2026-08-14): Replaced contributor-specific absolute checkout paths with repository-root and adjacent-checkout instructions; no implementation scope or validation evidence changed.
