from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.roles import UserRole
from app.dependencies import get_admin_accounts_service, get_current_user, get_settings
from app.main import create_app

URL = "/api/v1/me/statistikk-tilgang"


def _user(role: UserRole):
    return SimpleNamespace(
        auth_user_id=uuid4(), user_account_id=42, username="example",
        email="example@example.invalid", display_name="Example Person",
        role=role, is_impersonated=False,
    )


@pytest.fixture
def setup():
    app = create_app()
    accounts = SimpleNamespace(
        group_admin_groups=AsyncMock(return_value=[{"slug": "quiz", "name": "Quiz"}])
    )
    app.dependency_overrides[get_admin_accounts_service] = lambda: accounts
    return app, accounts


def _get(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app).get(URL, follow_redirects=False)


def test_admin_sees_every_group(setup):
    app, accounts = setup
    response = _get(app, _user(UserRole.ADMIN))
    assert response.status_code == 200
    assert response.json() == {"name": "Example Person", "role": "Admin", "groups": None}
    assert response.headers["cache-control"] == "private, no-store"
    accounts.group_admin_groups.assert_not_awaited()


def test_group_admin_is_scoped_to_assignment(setup):
    app, accounts = setup
    user = _user(UserRole.GROUP_ADMIN)
    response = _get(app, user)
    assert response.json()["groups"] == [{"slug": "quiz", "name": "Quiz"}]
    accounts.group_admin_groups.assert_awaited_once_with(user.auth_user_id)


@pytest.mark.parametrize("role", [UserRole.VOLUNTEER, UserRole.VIEWER])
def test_other_roles_are_refused(setup, role):
    app, _ = setup
    assert _get(app, _user(role)).status_code == 403


def test_anonymous_is_unauthorized(setup):
    app, _ = setup
    assert _get(app, None).status_code == 401


def test_dashboard_entry_redirects_to_website(setup):
    app, _ = setup
    settings = app.state.container.settings.model_copy(
        update={"website_base_url": "https://web.example.invalid/"}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.GROUP_ADMIN)
    response = TestClient(app).get("/statistikk", follow_redirects=False)
    assert response.headers["location"] == "https://web.example.invalid/nb/arrangementer/statistikk"
    app.dependency_overrides[get_current_user] = lambda: None
    response = TestClient(app).get("/statistikk", follow_redirects=False)
    assert response.headers["location"] == "/login?next=/statistikk"
