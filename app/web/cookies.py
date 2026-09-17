from __future__ import annotations

from fastapi import Request


def resolve_cookie_domain(
    request: Request, configured_domain: str | None
) -> str | None:
    """Return the ``Domain`` attribute to use for a cookie on this request.

    Browsers reject a ``Set-Cookie`` header whose ``Domain`` attribute is not
    the request host or a parent of it. The configured shared domain (for
    example ``.samfunnetibergen.no``) therefore only applies when the request
    actually arrives on that domain.

    The application is also served through the ``personal.kvarteret.no`` alias.
    Sending the shared domain there makes the browser drop the session cookie,
    so login appears to succeed but the browser returns to the login page. In
    that case the cookie must fall back to host-only scope.
    """

    normalized = (configured_domain or "").strip()
    candidate = normalized.lower().lstrip(".")
    hostname = (request.url.hostname or "").strip().lower()
    if not candidate or not hostname:
        return None
    if hostname == candidate or hostname.endswith(f".{candidate}"):
        return normalized
    return None
