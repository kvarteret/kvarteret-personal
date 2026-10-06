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


async def test_personal_account_role_cannot_bypass_access_configuration(monkeypatch):
    from app.domain.admin_accounts.service import AdminAccountsService

    monkeypatch.setattr("app.domain.admin_accounts.service._normalize_email", lambda value: value)
    repository = AdminAccountsRepository()
    repository.get_admin_account_detail = AsyncMock(return_value=SimpleNamespace(
        email="same", volunteer_id=10, is_legacy_account=False, role=UserRole.ADMIN))
    repository.update_admin_account = AsyncMock()
    service = AdminAccountsService(repository)
    with pytest.raises(ValueError, match="Tilgang i personaldatabasen"):
        await service.update_admin_account(user_account_id=10, username="person", email="same",
            display_name="Person", role=UserRole.GROUP_ADMIN)
    repository.update_admin_account.assert_not_awaited()


@pytest.mark.parametrize("names, memberships, expected", [
    (["Quiz"], [298], [298, 300]),
    (["Administrasjonen", "Quiz"], [], None),
    (["Hovedstyret"], [], None),
    ([], [], []),
])
async def test_application_group_defaults_follow_current_associations(names, memberships, expected):
    repository = AdminAccountsRepository()
    repository.get_admin_account_detail = AsyncMock(return_value=SimpleNamespace(
        volunteer_id=10, role=UserRole.ADMIN, group_admin_group_ids=memberships))
    repository.fetch_all_mappings = AsyncMock(return_value=[{"id": 300 + i, "name": name} for i, name in enumerate(names)])
    repository.access_groups = AsyncMock(return_value=[{"id": i} for i in [298, 300, 301]])
    assert await repository.application_group_filter(10, 20262) == expected
    statement = str(repository.fetch_all_mappings.call_args.args[0])
    assert "role_assignments.semester =" in statement


async def test_archived_groups_are_excluded_from_application_defaults():
    repository = AdminAccountsRepository()
    repository.get_admin_account_detail = AsyncMock(return_value=SimpleNamespace(
        volunteer_id=10, role=UserRole.GROUP_ADMIN, group_admin_group_ids=[100, 200]))
    repository.fetch_all_mappings = AsyncMock(return_value=[])
    repository.access_groups = AsyncMock(return_value=[{"id": 100}])
    assert await repository.application_group_filter(10, 20262) == [100]
    assert "groups.is_active IS true" in str(repository.fetch_all_mappings.call_args.args[0])


async def test_access_group_selector_queries_only_active_groups():
    repository = AdminAccountsRepository()
    repository.fetch_all_mappings = AsyncMock(return_value=[])
    await repository.access_groups()
    assert "groups.is_active IS true" in str(repository.fetch_all_mappings.call_args.args[0])
