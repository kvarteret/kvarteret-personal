"""Middleware that adds security headers to every response.

Uses Starlette's ``BaseHTTPMiddleware`` rather than a hand-rolled ASGI
middleware to stay consistent with the existing middleware in ``app/main.py``.

Headers added in all environments:
- ``X-Content-Type-Options: nosniff``
- ``X-Frame-Options: DENY``
- ``Referrer-Policy: strict-origin-when-cross-origin``

On HTML responses (text/html content-type):
- ``Content-Security-Policy`` allowing self-hosted assets, unpkg (htmx),
  jsdelivr (Alpine.js, ECharts), and inline scripts/styles required by
  the admin UI templates.

In production only:
- ``Strict-Transport-Security: max-age=31536000; includeSubDomains``
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# The admin UI loads HTMX and Alpine.js inline scripts plus ECharts from CDN.
# 'unsafe-inline' is required until templates are refactored to use nonces or
# external script files.
_ADMIN_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        # Only set CSP on HTML responses — API JSON responses don't need it
        # and email templates are rendered as email bodies, not web pages.
        content_type = headers.get("content-type", "")
        if "text/html" in content_type or "text/html" in str(response.media_type or ""):
            headers.setdefault("Content-Security-Policy", _ADMIN_CSP)

        if request.url.scheme == "https" or request.headers.get(
            "X-Forwarded-Proto", ""
        ) == "https":
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
