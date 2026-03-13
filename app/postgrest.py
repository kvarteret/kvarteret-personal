from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.errors import NotConfiguredError


class PostgrestClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise NotConfiguredError("Supabase credentials are required for PostgREST access.")
        self.settings = settings
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.client = client

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

        client = self._get_client()
        response = await client.get(f"/{table}", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise NotConfiguredError("PostgREST did not return a row list.")
        return payload

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "apikey": self.settings.supabase_secret_key,
                    "Authorization": f"Bearer {self.settings.supabase_secret_key}",
                    "Accept": "application/json",
                    "Accept-Profile": "public",
                },
                timeout=10.0,
            )
        return self.client
