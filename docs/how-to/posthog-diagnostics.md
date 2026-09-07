# Inspect Kvarteret Personal in PostHog

The shared EU project is [Samfunnet i Bergen, 202551](https://eu.posthog.com/project/202551).
On 2026-09-07, production ingestion was verified under service
`kvarteret-personal`; Vercel's team drain APIs returned no configured drains.

## Find logs and exceptions

Open [Logs](https://eu.posthog.com/project/202551/logs), choose service
`kvarteret-personal`, and select the time range. Filter severity to error/warn.
New log records expose sanitized fields such as `event`, `error_category`,
`registration_id`, and `request_id` as attributes, as well as in the JSON body.
Use `trace_id` or `registration_id` to correlate volunteer intake across apps.

Open [Error Tracking](https://eu.posthog.com/project/202551/error_tracking) and
filter event property `service` to `kvarteret-personal`. After deploying the
exception integration, `logger.exception` and ERROR records with `exc_info`
produce exception issues. Unhandled request exceptions use this same path.
Ordinary 4xx responses and log records without an exception do not create issues.
Browser reports through `/api/v1/telemetry/client-errors` remain in Logs.

Exception issues contain exception types and stack frame file/function/line
metadata. Messages, source context, local variables, request payloads, and user
identity are excluded. A fixed server distinct ID avoids creating personnel
profiles; affected-user counts therefore do not represent individual people.
The SDK can deduplicate repeated capture of the same exception object.

## Configuration and delivery

Set `POSTHOG_OBSERVABILITY_ENABLED=true`, the shared project's
`POSTHOG_PROJECT_TOKEN`, `POSTHOG_HOST=https://eu.i.posthog.com`, and
`OTEL_SERVICE_NAME=kvarteret-personal` in the desired Vercel environment, then
redeploy. Production already had these variables when inspected. Preview must
be configured separately. Never use a personal PostHog API key for ingestion.

`app/telemetry.py` exports sanitized logs and sampled traces. Its ASGI middleware
awaits provider flushes when each request finishes, including failures, rather
than relying only on background timers. Exports remain best-effort: abrupt
process termination or network failure can lose data. `app/error_tracking.py`
sends exceptions synchronously with a two-second HTTP timeout and no retries;
this can add latency to error paths. Normal requests do not send exception events.
Environment metadata uses `VERCEL_ENV` when available, otherwise `APP_ENV`.

The sibling implementation is in
`samfunnetibergen/apps/web/instrumentation.node.ts` (OTLP service
`samfunnetibergen`) and `apps/web/src/lib/observability.ts` (operational fields
and trace propagation). Its setup report links the same PostHog project.

## Vercel drains are a separate integration

The current connection sends application telemetry directly to PostHog. It does
not forward Vercel build, firewall, or platform logs. Vercel log drains send
JSON/NDJSON, while PostHog Logs accepts OTLP; do not point a Vercel log drain at
`/i/v1/logs` directly. PostHog's Vercel source webhook instead captures events,
which is distinct from the Logs product.

To add platform coverage later, configure an authenticated compatible receiver
with explicit project/source scope, filtering of personnel paths and query
strings, and duplicate handling for runtime logs already exported by the app.

References: [Python error tracking](https://posthog.com/docs/error-tracking/installation/python),
[Python logs](https://posthog.com/docs/logs/installation/python),
[Vercel source webhook](https://posthog.com/docs/cdp/source_webhooks/source-vercel-log-drain),
[Vercel drain formats](https://vercel.com/docs/drains/using-drains).
