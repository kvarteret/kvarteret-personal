from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.roles import UserRole
from app.dependencies import get_admin_accounts_service, get_current_user, get_mobile_card_service, get_session_store
from app.main import create_app
from tests.support.helpers import prime_csrf, csrf_headers


@pytest.fixture
def setup():
    app = create_app()
    subject = SimpleNamespace(is_review=False, person_id=10, trial_application_id=None)
    service = SimpleNamespace(
        request_access_code=AsyncMock(), create_session=AsyncMock(return_value=SimpleNamespace(session_token='signed')),
        sessions=SimpleNamespace(decode_token=lambda token: subject))
    account = SimpleNamespace(auth_user_id=uuid4(), user_account_id=91, is_legacy_account=False,
        username='example', email=None, display_name='Example Person', role=UserRole.GROUP_ADMIN)
    accounts = SimpleNamespace(get_individual_account=AsyncMock(return_value=account))
    sessions = SimpleNamespace(create_session=AsyncMock(return_value=SimpleNamespace(session_id='web-session')))
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_mobile_card_service] = lambda: service
    app.dependency_overrides[get_admin_accounts_service] = lambda: accounts
    app.dependency_overrides[get_session_store] = lambda: sessions
    client = TestClient(app)
    prime_csrf(client, path='/login')
    return client, subject, accounts, sessions


def test_login_pane_has_both_methods(setup):
    client, *_ = setup
    page = client.get('/login')
    assert '/login/app/code' in page.text
    assert 'Logg inn med passord' in page.text


def test_verified_volunteer_gets_its_linked_account_session(setup):
    client, subject, accounts, sessions = setup
    response = client.post('/login/app', data={'email': 'example', 'access_code': '123456', 'next': '//outside.invalid'},
                           headers=csrf_headers(client), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/'
    accounts.get_individual_account.assert_awaited_once_with(subject.person_id)
    assert sessions.create_session.call_args.kwargs['user_account_id'] == 91


@pytest.mark.parametrize('changes', [dict(is_review=True), dict(person_id=None, trial_application_id=1), dict(person_id=0)])
def test_review_and_trial_identities_cannot_enter_admin_panel(setup, changes):
    client, subject, accounts, sessions = setup
    for name, value in changes.items():
        setattr(subject, name, value)
    response = client.post('/login/app', data={'email': 'example', 'access_code': '123456'}, headers=csrf_headers(client))
    assert response.status_code == 401
    accounts.get_individual_account.assert_not_awaited()
    sessions.create_session.assert_not_awaited()


def test_unlinked_volunteer_has_no_admin_session(setup):
    client, _, accounts, sessions = setup
    accounts.get_individual_account.return_value = None
    response = client.post('/login/app', data={'email': 'example', 'access_code': '123456'}, headers=csrf_headers(client))
    assert response.status_code == 401
    sessions.create_session.assert_not_awaited()


def test_app_login_requires_csrf(setup):
    client, *_ = setup
    assert client.post('/login/app', data={'email': 'example', 'access_code': '123456'}).status_code == 403


def test_request_code_uses_updated_confirmation(setup):
    client, *_ = setup
    response = client.post('/login/app/code', data={'email': 'example'}, headers=csrf_headers(client))
    assert response.status_code == 200
    assert 'Sjekk din e-post!' in response.text
    assert 'name="access_code"' in response.text
