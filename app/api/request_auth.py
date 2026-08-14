from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings
from app.db.rate_limit import RateLimiter, RateLimitExceeded
from app.dependencies import get_rate_limiter, get_settings

VOLUNTEER_PROSPECT_PATH = "/api/v1/volunteer-prospects"
VOLUNTEER_PROSPECT_SIGNATURE_MAX_AGE_SECONDS = 300
_VOLUNTEER_PROSPECT_NONCE_WINDOW_SECONDS = 600
_SIGNATURE_PATTERN = re.compile(r"^v1=[0-9a-f]{64}$")

logger = logging.getLogger(__name__)

volunteer_prospect_signature_header = APIKeyHeader(
    name="X-Kvarteret-Signature",
    scheme_name="VolunteerProspectHmac",
    description=(
        "HMAC-SHA256 signature over the versioned request canonical form. "
        "Only the samfunnetibergen server holds the signing secret."
    ),
    auto_error=False,
)


def build_volunteer_prospect_canonical_message(
    *,
    timestamp: str,
    nonce: str,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    body_digest = hashlib.sha256(body).hexdigest()
    return "\n".join(
        ("v1", timestamp, nonce, method.upper(), path, body_digest)
    ).encode()


def build_volunteer_prospect_signature(
    secret: str,
    *,
    timestamp: str,
    nonce: str,
    method: str,
    path: str,
    body: bytes,
) -> str:
    canonical_message = build_volunteer_prospect_canonical_message(
        timestamp=timestamp,
        nonce=nonce,
        method=method,
        path=path,
        body=body,
    )
    digest = hmac.new(secret.encode(), canonical_message, hashlib.sha256).hexdigest()
    return f"v1={digest}"


async def require_signed_volunteer_prospect(
    request: Request,
    signature_header: Annotated[
        str | None,
        Security(volunteer_prospect_signature_header),
    ] = None,
    settings: Settings = Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    timestamp_header = request.headers.get("X-Kvarteret-Timestamp")
    nonce_header = request.headers.get("X-Kvarteret-Nonce")
    secrets = tuple(
        secret
        for secret in (
            settings.volunteer_prospect_hmac_secret,
            settings.volunteer_prospect_hmac_previous_secret,
        )
        if secret
    )
    if not secrets:
        logger.error("Volunteer prospect HMAC authentication is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable.",
        )

    if not timestamp_header or not nonce_header or not signature_header:
        _raise_authentication_failed("missing_header")
    if len(timestamp_header) > 16 or not timestamp_header.isascii():
        _raise_authentication_failed("invalid_timestamp")
    try:
        timestamp = int(timestamp_header)
    except ValueError:
        _raise_authentication_failed("invalid_timestamp")
    if str(timestamp) != timestamp_header:
        _raise_authentication_failed("invalid_timestamp")
    if abs(int(time.time()) - timestamp) > VOLUNTEER_PROSPECT_SIGNATURE_MAX_AGE_SECONDS:
        _raise_authentication_failed("stale_timestamp")

    try:
        parsed_nonce = UUID(nonce_header)
    except ValueError:
        _raise_authentication_failed("invalid_nonce")
    if str(parsed_nonce) != nonce_header:
        _raise_authentication_failed("invalid_nonce")
    if not _SIGNATURE_PATTERN.fullmatch(signature_header):
        _raise_authentication_failed("invalid_signature_format")

    body = await request.body()
    signature_matches = any(
        hmac.compare_digest(
            signature_header,
            build_volunteer_prospect_signature(
                secret,
                timestamp=timestamp_header,
                nonce=nonce_header,
                method=request.method,
                path=request.url.path,
                body=body,
            ),
        )
        for secret in secrets
    )
    if not signature_matches:
        _raise_authentication_failed("signature_mismatch")

    nonce_key = hashlib.sha256(nonce_header.encode()).hexdigest()
    try:
        await rate_limiter.hit(
            f"volunteer-prospect-nonce:{nonce_key}",
            limit=1,
            window_seconds=_VOLUNTEER_PROSPECT_NONCE_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        _raise_authentication_failed("replayed_nonce")
    except Exception as exc:
        logger.exception("Volunteer prospect replay protection failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable.",
        ) from exc


def _raise_authentication_failed(reason: str) -> NoReturn:
    logger.warning(
        "Rejected volunteer prospect request authentication.",
        extra={"authentication_failure_reason": reason},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Request authentication failed.",
        headers={"WWW-Authenticate": "HMAC"},
    )
