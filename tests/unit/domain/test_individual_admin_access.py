from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.auth.roles import UserRole
from app.domain.admin_accounts.repository import AdminAccountsRepository


@pytest.fixture
def repository():
    repository = AdminAccountsRepository()
    repository.get_admin_account_detail = AsyncMock(return_value=SimpleNamespace(
        auth_user_id=uuid4(), email='same', is_legacy_account=False))
    repository.volunteer_identity = AsyncMock(return_value={'email': 'same'})
    repository.account_for_volunteer = AsyncMock(return_value=10)
    repository.access_groups = AsyncMock(return_value=[{'id': 100}])
    repository.execute = AsyncMock()
    return repository


@pytest.mark.parametrize('case', ['legacy', 'email_mismatch', 'different_account', 'missing_group', 'unknown_group'])
async def test_invalid_access_updates_do_not_write(repository, case):
    groups = [100]
    if case == 'legacy':
        repository.get_admin_account_detail.return_value.is_legacy_account = True
    elif case == 'email_mismatch':
        repository.volunteer_identity.return_value['email'] = 'different'
    elif case == 'different_account':
        repository.account_for_volunteer.return_value = 20
    elif case == 'missing_group':
        groups = []
    else:
        groups = [200]
    with pytest.raises(ValueError):
        await repository.configure_access(10, 1, UserRole.GROUP_ADMIN, groups)
    repository.execute.assert_not_awaited()


async def test_group_admin_update_replaces_groups_and_invalidates_sessions(repository):
    await repository.configure_access(10, 1, UserRole.GROUP_ADMIN, [100, 100])
    statements = [str(call.args[0]) for call in repository.execute.call_args_list]
    assert sum('INSERT INTO public.group_admin_memberships' in statement for statement in statements) == 1
    assert any('DELETE FROM public.group_admin_memberships' in statement for statement in statements)
    assert any('DELETE FROM public.web_sessions' in statement for statement in statements)
