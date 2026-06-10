"""Middleware that adds security headers to every response.

Uses Starlette's ``BaseHTTPMiddleware`` rather than a hand-rolled ASGI
middleware to stay consistent with the existing middleware in ``app/main.py``.

Headers added in all environments:
- ``X-Content-Type-Options: nosniff``
- ``X-Frame-Options: DENY``
- ``Referrer-Policy: strict-origin-when-cross-origin``

In production only:
- ``Strict-Transport-Security: max-age=31536000; includeSubDomains``
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        if request.url.scheme == "https" or request.headers.get(
            "X-Forwarded-Proto", ""
        ) == "https":
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
