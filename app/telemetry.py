from __future__ import annotations

import logging
import os

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
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.config import Settings
from app.observability import JsonLogFormatter

logger = logging.getLogger(__name__)
_httpx_instrumented = False
_TRACE_SAMPLE_RATE = 0.1


class _SanitizedLoggingHandler(LoggingHandler):
    """Export only the already-sanitized JSON body, never raw log extras."""

    def emit(self, record: logging.LogRecord) -> None:
        safe_record = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=JsonLogFormatter().format(record),
            args=(),
            exc_info=None,
            func=record.funcName,
        )
        super().emit(safe_record)


def _build_trace_provider(resource: Resource) -> TracerProvider:
    return TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(_TRACE_SAMPLE_RATE)),
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
                "deployment.environment.name": settings.app_env,
                "service.version": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
                "vercel.deployment.id": os.getenv("VERCEL_DEPLOYMENT_ID", "unknown"),
                "cloud.region": os.getenv("VERCEL_REGION", "unknown"),
            }
        )
        trace_provider = _build_trace_provider(resource)
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

        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace_provider)
        if not _httpx_instrumented:
            HTTPXClientInstrumentor().instrument(tracer_provider=trace_provider)
            _httpx_instrumented = True
    except Exception:
        # Telemetry is never authoritative and must not prevent app startup.
        logger.warning(
            "telemetry.configuration.failed",
            extra={
                "event": "telemetry.configuration.failed",
                "event_data": {"error_category": "configuration"},
            },
        )
