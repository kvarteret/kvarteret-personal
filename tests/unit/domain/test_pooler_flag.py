from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.db.pooler_flag import FLAG_KEY, build_percentage_provider


@pytest.mark.parametrize('payload,enabled,expected', [
    ('{"percentage":5}', True, 5),
    ({'percentage':100}, True, 100),
    ({'percentage':5}, False, 0),
    ({'percentage':101}, True, 0),
    ({'percentage':True}, True, 0),
    ('invalid', True, 0),
])
async def test_payload_validation(monkeypatch, payload, enabled, expected):
    post = AsyncMock(return_value=httpx.Response(200, request=httpx.Request('POST','https://example.test'), json={
        'flags': {FLAG_KEY: {'enabled':enabled,'metadata':{'payload':payload}}},
    }))
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    settings = Settings(_env_file=None, database_transaction_pooler_enabled=True, posthog_project_token='test')
    provider = build_percentage_provider(settings)
    assert await provider() == expected
    assert await provider() == expected
    assert post.await_count == 1


async def test_expired_value_fails_closed_and_recovers(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.db.pooler_flag.time.monotonic', lambda: clock[0])
    response = httpx.Response(200, request=httpx.Request('POST','https://example.test'), json={
        'flags': {FLAG_KEY: {'enabled':True,'metadata':{'payload':{'percentage':5}}}},
    })
    post = AsyncMock(side_effect=[response, TimeoutError(), response])
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    provider = build_percentage_provider(Settings(_env_file=None, database_transaction_pooler_enabled=True, posthog_project_token='test'))
    assert await provider() == 5
    clock[0] += 31
    assert await provider() == 0
    clock[0] += 31
    assert await provider() == 5


async def test_emergency_switch_avoids_posthog(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    assert await build_percentage_provider(Settings(_env_file=None, posthog_project_token='test'))() == 0
    post.assert_not_called()
