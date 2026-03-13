from __future__ import annotations

import pytest

from app.db.session import dispose_database_runtime


@pytest.fixture(autouse=True)
async def dispose_database_runtime_between_tests():
    yield
    await dispose_database_runtime()
