from __future__ import annotations

import logging
import os
import json

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
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.error_tracking import configure_error_tracking
from app.observability import JsonLogFormatter, emit_event

logger = logging.getLogger(__name__)
_httpx_instrumented = False
_TRACE_SAMPLE_RATE = 0.1


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
                for provider in self.providers:
                    try:
                        await run_in_threadpool(
                            provider.force_flush, timeout_millis=2000
                        )
                    except Exception:
                        pass


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
        ALWAYS_ON
        if sample_rate >= 1.0
        else ParentBased(TraceIdRatioBased(sample_rate))
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
        trace_provider = _build_trace_provider(
            resource, sample_rate=_TRACE_SAMPLE_RATE
        )
        trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{settings.posthog_host.rstrip('/')}/i/v1/traces",
                    headers=headers,
                    timeout=5,
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
                    timeout=5,
                ),
                schedule_delay_millis=1000,
            )
        )
        logging.getLogger().addHandler(
            _SanitizedLoggingHandler(
                level=logging.NOTSET, logger_provider=logger_provider
            )
        )

        configure_error_tracking(settings)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace_provider)
        install_telemetry_flush(app, (trace_provider, logger_provider))
        if not _httpx_instrumented:
            HTTPXClientInstrumentor().instrument(tracer_provider=trace_provider)
            _httpx_instrumented = True
    except Exception:
        # Telemetry is never authoritative and must not prevent app startup.
        emit_event(
            logger,
            "telemetry.configuration.failed",
            level=logging.WARNING,
            fields={"error_category": "configuration", "outcome": "failure"},
        )
