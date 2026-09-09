"""PostHog exception issues without personnel data or exception messages."""

from __future__ import annotations

import json
import logging
import os

from posthog import Posthog

from app.config import Settings
from app.observability import JsonLogFormatter


def sanitize_exception_event(event: dict) -> dict | None:
    if event.get("event") != "$exception":
        return None
    properties = event.get("properties", {})
    exceptions = []
    for exception in properties.get("$exception_list", []):
        frames = [
            {
                key: frame[key]
                for key in (
                    "filename",
                    "function",
                    "module",
                    "lineno",
                    "in_app",
                    "platform",
                )
                if key in frame
            }
            for frame in exception.get("stacktrace", {}).get("frames", [])
        ]
        exceptions.append(
            {
                "type": exception.get("type", "Error"),
                "value": "Exception message withheld",
                "mechanism": exception.get(
                    "mechanism", {"type": "generic", "handled": True}
                ),
                "stacktrace": {"type": "raw", "frames": frames},
            }
        )
    # Rebuild from an allowlist: SDK contexts must not add identities or payloads.
    safe = {
        key: properties[key]
        for key in (
            "service",
            "environment",
            "release",
            "request_id",
            "route_template",
            "http_method",
            "trace_id",
            "span_id",
            "$trace_id",
            "$span_id",
            "$lib",
            "$lib_version",
            "logger",
            "form_id",
            "attempt_count",
            "validation_fields",
            "validation_codes",
            "error_source",
            "status_code",
        )
        if key in properties
    }
    safe.update(
        {
            "$exception_list": exceptions,
            "$process_person_profile": False,
            "$geoip_disable": True,
        }
    )
    event["properties"] = safe
    event["distinct_id"] = "kvarteret-personal-server"
    return event


class ExceptionLoggingHandler(logging.Handler):
    def __init__(self, client: Posthog, settings: Settings):
        super().__init__(level=logging.ERROR)
        self.client = client
        self.settings = settings

    def emit(self, record: logging.LogRecord) -> None:
        # Exporter failures must never recurse into the exporter.
        if not record.name.startswith("app.") or not record.exc_info:
            return
        try:
            properties = json.loads(JsonLogFormatter().format(record))
            properties.update(
                {
                    "service": self.settings.otel_service_name,
                    "environment": os.getenv("VERCEL_ENV") or self.settings.app_env,
                    "release": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
                }
            )
            self.client.capture_exception(record.exc_info, properties=properties)
        except Exception:
            # Reporting failure cannot change application behavior.
            pass


def configure_error_tracking(settings: Settings) -> None:
    client = Posthog(
        settings.posthog_project_token,
        host=settings.posthog_host,
        # Errors are rare: bounded synchronous delivery avoids losing queued
        # exceptions when Vercel freezes an idle function.
        sync_mode=True,
        timeout=2,
        max_retries=0,
        enable_exception_autocapture=False,
        capture_exception_code_variables=False,
        before_send=sanitize_exception_event,
    )
    logging.getLogger().addHandler(ExceptionLoggingHandler(client, settings))
