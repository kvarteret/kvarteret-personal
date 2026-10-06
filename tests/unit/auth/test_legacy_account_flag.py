import pytest
from sqlalchemy.dialects import postgresql

from app.auth.repository import DatabaseAuthRepository
from app.config import Settings


class CapturingRepository(DatabaseAuthRepository):
    async def fetch_first_mapping(self, stmt):
        self.sql = str(stmt.compile(dialect=postgresql.dialect()))
        return None


@pytest.mark.parametrize('enabled', [True, False])
async def test_flag_controls_identifier_and_session_queries(enabled):
    repository = CapturingRepository(legacy_login_enabled=enabled)
    assert await repository.get_user_account_by_identifier('example') is None
    assert ('is_legacy_account IS false' in repository.sql) == (not enabled)
    assert await repository.load_authenticated_user_for_session('example-session') is None
    where = repository.sql.split('WHERE', 1)[1]
    assert ('is_legacy_account IS false' in where) == (not enabled)
    if not enabled:
        assert 'impersonator_accounts.is_legacy_account IS false' in where


def test_legacy_logins_default_to_enabled(monkeypatch):
    monkeypatch.delenv('LEGACY_ADMIN_LOGIN_ENABLED', raising=False)
    assert Settings(_env_file=None).legacy_admin_login_enabled
