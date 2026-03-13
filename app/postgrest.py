from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from app.config import Settings, get_settings


class PostgrestClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise RuntimeError("Supabase credentials are required for PostgREST access.")
        self.settings = settings
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "apikey": settings.supabase_secret_key,
                "Authorization": f"Bearer {settings.supabase_secret_key}",
                "Accept": "application/json",
                "Accept-Profile": "public",
            },
            timeout=10.0,
        )

    async def select_rows(
        self,
        table: str,
        *,
        select: str,
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)

        response = await self.client.get(f"/{table}", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("PostgREST did not return a row list.")
        return payload


@lru_cache(maxsize=1)
def get_postgrest_client() -> PostgrestClient:
    return PostgrestClient(get_settings())
