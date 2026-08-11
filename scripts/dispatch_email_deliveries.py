"""Dispatch one batch of due email deliveries without Vercel Cron."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from app.db.session import session_scope
from app.runtime import build_application_container


async def _main() -> None:
    container = build_application_container()
    try:
        runtime = container.database_runtime_manager.get_runtime()
        async with session_scope(runtime):
            summary = await container.email_outbox_service.dispatch_due(batch_size=10)
        output = asdict(summary)
        output["delivery_ids"] = [str(value) for value in summary.delivery_ids]
        print(json.dumps(output, sort_keys=True))
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(_main())
