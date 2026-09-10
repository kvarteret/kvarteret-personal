from __future__ import annotations

import logging
import os
import json

import anyio

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ParentBased,
    TraceIdRatioBased,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.error_tracking import configure_error_tracking
from app.observability import (
    IsolatedLoggingHandler,
    JsonLogFormatter,
    _record_diagnostic,
    get_domain_logger,
)

logger = get_domain_logger(__name__)
_httpx_instrumented = False
_TRACE_SAMPLE_RATE = 0.01


class TelemetryFlushMiddleware:
    """Finish exporting before the invocation returns, including failed requests."""

    def __init__(self, app: ASGIApp, providers: tuple):
        self.app = app
        self.providers = providers

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            await self.app(scope, receive, send)
        finally:
            if scope["type"] == "http":
                async def flush(provider):
                    try:
                        result = await anyio.to_thread.run_sync(
                            lambda: provider.force_flush(timeout_millis=2000),
                            abandon_on_cancel=True,
                        )
                        if result is False:
                            _record_diagnostic("exporter_timeout")
                    except Exception:
                        _record_diagnostic("exporter_failure")

                with anyio.move_on_after(2) as budget:
                    async with anyio.create_task_group() as group:
                        for provider in self.providers:
                            group.start_soon(flush, provider)
                if budget.cancel_called:
                    _record_diagnostic("exporter_timeout")


def install_telemetry_flush(app: FastAPI, providers: tuple) -> None:
    # FastAPIInstrumentor wraps the user middleware stack. Wrap its completed
    # stack so even the HTTP server span has ended before flushing.
    build_stack = app.build_middleware_stack

    def build_flushing_stack():
        return TelemetryFlushMiddleware(build_stack(), providers)

    app.build_middleware_stack = build_flushing_stack


class _SanitizedLoggingHandler(LoggingHandler):
    """Export only the already-sanitized JSON body, never raw log extras."""

    def emit(self, record: logging.LogRecord) -> None:
        payload = json.loads(JsonLogFormatter().format(record))
        safe_record = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname=record.pathname,
            lineno=record.lineno,
            # The OTel body is the reviewed human-readable message. Structured
            # fields remain attributes so PostHog Logs can filter them.
            msg=payload.get("message", "Application event"),
            args=(),
            exc_info=None,
            func=record.funcName,
        )
        # Make sanitized diagnostic fields directly filterable in PostHog Logs.
        for key, value in payload.items():
            if key not in safe_record.__dict__ and key not in {"message", "timestamp"}:
                safe_record.__dict__[key] = value
        super().emit(safe_record)


def _build_trace_provider(
    resource: Resource, *, sample_rate: float = 1.0
) -> TracerProvider:
    sampler = (
        ALWAYS_ON if sample_rate >= 1.0 else ParentBased(TraceIdRatioBased(sample_rate))
    )
    return TracerProvider(
        resource=resource,
        sampler=sampler,
    )


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    """Install best-effort OTLP logs and traces for the current process."""
    global _httpx_instrumented
    if not settings.posthog_observability_enabled:
        return
    try:
        headers = {"Authorization": f"Bearer {settings.posthog_project_token}"}
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment.name": os.getenv("VERCEL_ENV")
                or settings.app_env,
                "service.version": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
                "vercel.deployment.id": os.getenv("VERCEL_DEPLOYMENT_ID", "unknown"),
                "cloud.region": os.getenv("VERCEL_REGION", "unknown"),
            }
        )
        trace_provider = _build_trace_provider(resource, sample_rate=_TRACE_SAMPLE_RATE)
        trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{settings.posthog_host.rstrip('/')}/i/v1/traces",
                    headers=headers,
                    timeout=2,
                ),
                schedule_delay_millis=1000,
            )
        )
        trace.set_tracer_provider(trace_provider)

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=f"{settings.posthog_host.rstrip('/')}/i/v1/logs",
                    headers=headers,
                    timeout=2,
                ),
                schedule_delay_millis=1000,
            )
        )
        logging.getLogger().addHandler(
            IsolatedLoggingHandler(
                _SanitizedLoggingHandler(
                    level=logging.NOTSET, logger_provider=logger_provider
                )
            )
        )

        configure_error_tracking(settings)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace_provider)
        providers = [trace_provider, logger_provider]
        # Metrics use the deployment's explicitly configured collector, not an
        # invented PostHog metrics URL. Unconfigured environments remain no-op.
        metrics_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
        if metrics_endpoint:
            from opentelemetry import metrics
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            meter_provider = MeterProvider(resource=resource, metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=metrics_endpoint, timeout=2),
                    export_interval_millis=60000,
                    export_timeout_millis=2000,
                )
            ])
            metrics.set_meter_provider(meter_provider)
            providers.append(meter_provider)
        install_telemetry_flush(app, tuple(providers))
        if not _httpx_instrumented:
            HTTPXClientInstrumentor().instrument(tracer_provider=trace_provider)
            _httpx_instrumented = True
    except Exception:
        # Telemetry is never authoritative and must not prevent app startup.
        logger.event(
            "telemetry.configuration.failed",
            fields={"error_category": "configuration", "outcome": "failure"},
        )
