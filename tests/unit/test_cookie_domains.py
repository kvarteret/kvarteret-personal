from __future__ import annotations

import pytest
from starlette.requests import Request

from app.web.cookies import resolve_cookie_domain


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "https",
            "method": "GET",
            "path": "/login",
            "query_string": b"",
            "headers": [(b"host", host.encode())],
            "server": (host, 443),
        }
    )


@pytest.mark.parametrize(
    ("configured_domain", "host", "expected"),
    [
        (None, "personal.kvarteret.no", None),
        ("", "personal.kvarteret.no", None),
        (".samfunnetibergen.no", "samfunnetibergen.no", ".samfunnetibergen.no"),
        (
            ".samfunnetibergen.no",
            "personal.samfunnetibergen.no",
            ".samfunnetibergen.no",
        ),
        (
            ".samfunnetibergen.no",
            "orakel.samfunnetibergen.no",
            ".samfunnetibergen.no",
        ),
        ("samfunnetibergen.no", "orakel.samfunnetibergen.no", "samfunnetibergen.no"),
        (".samfunnetibergen.no", "personal.kvarteret.no", None),
        (".samfunnetibergen.no", "evilsamfunnetibergen.no", None),
        (".samfunnetibergen.no", "samfunnetibergen.no.attacker.test", None),
        (".samfunnetibergen.no", "SAMFUNNETIBERGEN.NO", ".samfunnetibergen.no"),
    ],
)
def test_resolve_cookie_domain(
    configured_domain: str | None, host: str, expected: str | None
) -> None:
    assert resolve_cookie_domain(_request(host), configured_domain) == expected
