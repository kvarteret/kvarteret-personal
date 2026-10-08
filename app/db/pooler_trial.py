"""Connection-only Supabase transaction-pooler canary; never replay SQL."""

import logging
import random
import time
from collections.abc import Awaitable, Callable

import asyncpg
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db.pooler_flag import build_percentage_provider

logger = logging.getLogger(__name__)


def build_trial_connector(settings: Settings) -> Callable[[], Awaitable[asyncpg.Connection]]:
    url = make_url(settings.database_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or not (url.host or "").endswith(".pooler.supabase.com")
        or url.port != 5432
        or any(key in url.query for key in ("host", "port", "user", "database"))
    ):
        raise ValueError("The pooler trial requires a Supabase session-pooler URL on port 5432.")

    # Let SQLAlchemy translate URL options exactly as for the ordinary engine.
    _, fallback_kwargs = PGDialect_asyncpg().create_connect_args(url)
    fallback_kwargs.pop("prepared_statement_cache_size", None)
    fallback_kwargs.pop("prepared_statement_name_func", None)
    fallback_kwargs["statement_cache_size"] = 0
    trial_kwargs = {
        **fallback_kwargs,
        "port": 6543,
        "timeout": settings.database_transaction_pooler_connect_timeout_seconds,
    }
    get_percentage = build_percentage_provider(settings)
    retry_after = 0.0
    connecting_trial = False

    async def connect() -> asyncpg.Connection:
        nonlocal retry_after, connecting_trial
        if (
            not connecting_trial
            and time.monotonic() >= retry_after
            and random.randrange(100) < await get_percentage()
        ):
            # One trial handshake at a time per runtime limits failure bursts.
            connecting_trial = True
            started = time.monotonic()
            try:
                connection = await asyncpg.connect(**trial_kwargs)
            except Exception as exc:
                retry_after = time.monotonic() + settings.database_transaction_pooler_cooldown_seconds
                # Exception text can contain credentials; log only its type.
                logger.warning(
                    "database.pooler_trial.fallback",
                    extra={"event": "database.pooler_trial.fallback", "event_data": {
                        "error_category": type(exc).__name__,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }},
                )
            else:
                logger.info(
                    "database.pooler_trial.connected",
                    extra={"event": "database.pooler_trial.connected", "event_data": {
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }},
                )
                return connection
            finally:
                connecting_trial = False
        # This runs only before a DB connection is handed to SQLAlchemy. Once
        # SQL executes, failures propagate normally: transactions are not retried.
        return await asyncpg.connect(**fallback_kwargs)

    return connect
