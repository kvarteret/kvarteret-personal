from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.login_service import LoginResult
from app.auth.models import WebSession
from app.auth.roles import UserRole
from app.db.rate_limit import InMemoryRateLimiter
from app.dependencies import (
    get_current_user,
    get_login_service,
    get_mobile_card_april_state_service,
    get_password_reset_service,
    get_rate_limiter,
    get_session_store,
    get_volunteers_service,
    require_authenticated_user,
)
from app.main import create_app
from app.runtime import build_application_container
from app.domain.volunteers.models import VolunteerListItem, VolunteerListPage
from app.web.csrf import CSRF_COOKIE_NAME
from tests.support.helpers import csrf_headers, make_authenticated_user, prime_csrf


class FakeMobileCardAprilStateService:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.set_calls: list[dict[str, int | bool | None]] = []

    async def is_enabled(self) -> bool:
        return self.enabled

    async def set_enabled(
        self, *, enabled: bool, updated_by_user_account_id: int | None
    ) -> None:
        self.enabled = enabled
        self.set_calls.append(
            {
                "enabled": enabled,
                "updated_by_user_account_id": updated_by_user_account_id,
            }
        )


class FakeLoginService:
    async def login(self, *, identifier: str, password: str, ip_address: str | None, user_agent: str | None) -> LoginResult:
        return LoginResult(
            session=WebSession(
                session_id="session-123",
                auth_user_id=uuid4(),
                user_account_id=5,
                expires_at=datetime.now(UTC),
            ),
            user=make_authenticated_user(UserRole.ADMIN),
        )


class FakePasswordResetService:
    def __init__(self, *, delivered: bool = True, should_fail: bool = False) -> None:
        self.delivered = delivered
        self.should_fail = should_fail
        self.calls: list[dict[str, str]] = []

    async def send_reset_email(self, *, email: str, redirect_to: str) -> bool:
        self.calls.append({"email": email, "redirect_to": redirect_to})
        if self.should_fail:
            raise RuntimeError("upstream failure with sensitive details")
        return self.delivered


class FakeVolunteersService:
    async def list_volunteers(self, query: str | None = None, limit: int = 50) -> list[VolunteerListItem]:
        return (await self.list_volunteers_page(query=query, limit=limit, cursor=None)).items

    async def count_volunteers(self, query: str | None = None, only_active: bool = False) -> int:
        return len(
            (
                await self.list_volunteers_page(
                    query=query,
                    limit=50,
                    cursor=None,
                    only_active=only_active,
                )
            ).items
        )

    async def list_volunteers_page(
        self,
        query: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
        only_active: bool = False,
    ) -> VolunteerListPage:
        return VolunteerListPage(
            items=[
                VolunteerListItem(
                    volunteer_id=1,
                    first_name="Sample",
                    last_name="Person",
                    full_name="Sample Person",
                    email="person.one@example.test",
                    phone="00000000",
                    photo_url=None,
                )
            ],
            limit=limit,
            cursor=cursor,
            next_cursor=None,
        )

    async def get_volunteer_detail(self, volunteer_id: int):
        return None

    async def list_role_assignments(self, volunteer_id: int, limit: int = 12):
        return []

    async def get_volunteer_relations(self, volunteer_id: int):
        return None


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return None

    async def create_session(self, **kwargs):
        raise NotImplementedError

    async def delete_session(self, session_id: str) -> None:
        return None

    def invalidate_session_cache(self, session_id: str) -> None:
        return None


class MiddlewareSessionStore:
    def __init__(self, user) -> None:
        self.user = user

    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=self.user.auth_user_id,
                user_account_id=self.user.user_account_id,
                expires_at=datetime.now(UTC),
            ),
            self.user,
        )

    async def create_session(self, **kwargs):
        raise NotImplementedError

    async def delete_session(self, session_id: str) -> None:
        return None

    def invalidate_session_cache(self, session_id: str) -> None:
        return None


class ImpersonatedSessionStore:
    def __init__(self, user, impersonator_user) -> None:
        self.user = user
        self.impersonator_user = impersonator_user
        self.created_sessions = []
        self.deleted_sessions = []

    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=self.user.auth_user_id,
                user_account_id=self.user.user_account_id,
                expires_at=datetime.now(UTC),
                impersonator_user=self.impersonator_user,
            ),
            self.user,
        )

    async def create_session(
        self,
        *,
        auth_user_id,
        user_account_id,
        impersonator_auth_user_id=None,
        impersonator_user_account_id=None,
        ip_address,
        user_agent,
    ):
        self.created_sessions.append(
            {
                "auth_user_id": auth_user_id,
                "user_account_id": user_account_id,
                "impersonator_auth_user_id": impersonator_auth_user_id,
                "impersonator_user_account_id": impersonator_user_account_id,
            }
        )
        return WebSession(
            session_id="restored-admin-session",
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=datetime.now(UTC),
        )

    async def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)

    def invalidate_session_cache(self, session_id: str) -> None:
        return None


class FakePendingVolunteerApplicationsService:
    def __init__(self) -> None:
        self.calls = 0

    async def count_pending_volunteer_applications(self) -> int:
        self.calls += 1
        return 3


def test_login_sets_cookie_and_protected_page_renders() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_session_store] = lambda: FakeSessionStore()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    client = TestClient(app)

    login_response = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert "kvarteret_session" in login_response.headers["set-cookie"]

    dashboard_response = client.get("/")
    people_response = client.get("/volunteers")

    assert dashboard_response.status_code == 200
    assert "Admin-kontoer" in dashboard_response.text
    assert "Søknader" in dashboard_response.text
    assert people_response.status_code == 200
    assert "Sample Person" in people_response.text
    assert "Ny frivillig" in people_response.text


def test_login_page_links_to_password_reset_form() -> None:
    response = TestClient(create_app()).get("/login")

    assert response.status_code == 200
    assert 'action="/login"' in response.text
    assert 'hx-boost="false"' in response.text
    assert 'href="/forgot-password"' in response.text
    assert "Glemt passord?" in response.text


def test_login_form_renders_csrf_token_matching_cookie() -> None:
    client = TestClient(create_app())

    response = client.get("/login")

    assert response.status_code == 200
    token = client.cookies[CSRF_COOKIE_NAME]
    assert 'name="csrf_token"' in response.text
    assert f'value="{token}"' in response.text


def test_login_form_token_satisfies_csrf_with_stale_session_cookie() -> None:
    """A stale session cookie must not turn a valid login form into a 403.

    The login page is frequently reached through htmx-boosted navigation, so
    the hidden CSRF field has to be rendered server-side instead of relying on
    client-side injection.
    """
    container = build_application_container()
    app = create_app(container=container)
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    client = TestClient(app)

    page = client.get("/login")
    assert page.status_code == 200
    token = client.cookies[CSRF_COOKIE_NAME]
    client.cookies.set(container.settings.session_cookie_name, "inert-session-cookie")

    response = client.post(
        "/login",
        data={
            "identifier": "admin",
            "password": "Password123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


def _login_client_with_shared_cookie_domain(domain: str, base_url: str) -> TestClient:
    """Build a client whose app shares session cookies on ``domain``."""
    container = build_application_container()
    container.settings = container.settings.model_copy(
        update={"session_cookie_domain": domain}
    )
    app = create_app(container=container)
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    return TestClient(app, base_url=base_url)


def _session_cookie_header(response) -> str:
    headers = [
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith("kvarteret_session=")
    ]
    assert headers, response.headers.get_list("set-cookie")
    return headers[0]


def test_login_sets_host_only_session_cookie_on_kvarteret_alias() -> None:
    """The shared cookie domain must not be sent from the kvarteret.no alias.

    Browsers reject a Domain attribute that is not the request host, so a
    cookie scoped to ``.samfunnetibergen.no`` is dropped on
    ``personal.kvarteret.no`` and the user bounces back to the login page.
    """
    client = _login_client_with_shared_cookie_domain(
        ".samfunnetibergen.no", "https://personal.kvarteret.no"
    )

    response = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session_cookie = _session_cookie_header(response)
    assert "Domain=" not in session_cookie


def test_login_sets_shared_session_cookie_on_samfunnetibergen_subdomain() -> None:
    """A request on the shared parent domain keeps cross-subdomain SSO."""
    client = _login_client_with_shared_cookie_domain(
        ".samfunnetibergen.no", "https://personal.samfunnetibergen.no"
    )

    response = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session_cookie = _session_cookie_header(response)
    assert "Domain=.samfunnetibergen.no" in session_cookie


def test_login_on_kvarteret_alias_authenticates_followup_request() -> None:
    """Regression: the browser jar must accept the session cookie it is sent.

    ``http.cookiejar`` (used by real browsers and by httpx) rejects a cookie
    whose ``Domain`` attribute does not match the request host, so the earlier
    shared-domain-only behavior produced a login loop on the kvarteret.no
    alias: login returned 303, but the next request had no session.
    """
    container = build_application_container()
    container.settings = container.settings.model_copy(
        update={"session_cookie_domain": ".samfunnetibergen.no"}
    )
    container.session_store = MiddlewareSessionStore(make_authenticated_user())
    app = create_app(container=container)
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    client = TestClient(app, base_url="https://personal.kvarteret.no")

    login = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 200


def test_logout_deletes_the_same_host_only_cookie_it_created() -> None:
    client = _login_client_with_shared_cookie_domain(
        ".samfunnetibergen.no", "https://personal.kvarteret.no"
    )
    container = client.app.state.container
    container.session_store = MiddlewareSessionStore(make_authenticated_user())
    prime_csrf(
        client,
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id(
                "session-123"
            )
        },
    )

    response = client.post(
        "/logout", headers=csrf_headers(client), follow_redirects=False
    )

    assert response.status_code == 303
    session_cookie = _session_cookie_header(response)
    assert "Domain=" not in session_cookie


def test_forgot_password_form_renders_csrf_token_matching_cookie() -> None:
    client = TestClient(create_app())

    response = client.get("/forgot-password")

    assert response.status_code == 200
    token = client.cookies[CSRF_COOKIE_NAME]
    assert 'name="csrf_token"' in response.text
    assert f'value="{token}"' in response.text


def test_password_reset_page_renders() -> None:
    response = TestClient(create_app()).get("/forgot-password")

    assert response.status_code == 200
    assert "Send tilbakestillingslenke" in response.text
    assert 'type="email"' in response.text
    assert 'action="/forgot-password"' in response.text
    assert 'hx-boost="false"' in response.text


def test_password_reset_submission_calls_service_and_returns_generic_message() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_password_reset_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    client = TestClient(app)

    response = client.post(
        "/forgot-password",
        data={"email": " ADMIN@example.com "},
        follow_redirects=False,
    )
    confirmation = client.get(response.headers["location"])

    assert response.status_code == 303
    assert response.headers["location"] == "/forgot-password?sent=1"
    assert service.calls == [
        {
            "email": "admin@example.com",
            "redirect_to": "http://testserver/set-password",
        }
    ]
    assert confirmation.status_code == 200
    assert "Hvis e-postadressen tilhører en konto" in confirmation.text


def test_password_reset_response_does_not_reveal_delivery_failure() -> None:
    responses = []
    for service in (
        FakePasswordResetService(delivered=False),
        FakePasswordResetService(should_fail=True),
    ):
        app = create_app()
        app.dependency_overrides[get_password_reset_service] = lambda: service
        app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
        responses.append(
            TestClient(app).post(
                "/forgot-password",
                data={"email": "unknown@example.com"},
                follow_redirects=False,
            )
        )

    assert [
        (response.status_code, response.headers["location"]) for response in responses
    ] == [
        (303, "/forgot-password?sent=1"),
        (303, "/forgot-password?sent=1"),
    ]


def test_password_reset_rejects_invalid_email() -> None:
    app = create_app()
    service = FakePasswordResetService()
    app.dependency_overrides[get_password_reset_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()

    response = TestClient(app).post(
        "/forgot-password",
        data={"email": "not-an-email"},
    )

    assert response.status_code == 400
    assert "Skriv inn en gyldig e-postadresse" in response.text
    assert service.calls == []


def test_password_reset_is_rate_limited() -> None:
    app = create_app()
    service = FakePasswordResetService()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_password_reset_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client = TestClient(app)

    for _ in range(5):
        assert (
            client.post(
                "/forgot-password",
                data={"email": "admin@example.com"},
                follow_redirects=False,
            ).status_code
            == 303
        )

    response = client.post(
        "/forgot-password",
        data={"email": "admin@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 429
    assert "For mange forespørsler" in response.text
    assert len(service.calls) == 5


def test_group_admin_sees_registrations_and_new_volunteer_but_not_admin_accounts() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.GROUP_ADMIN)
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_session_store] = lambda: FakeSessionStore()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    client = TestClient(app)

    dashboard_response = client.get("/")
    people_response = client.get("/volunteers")

    assert dashboard_response.status_code == 200
    assert "Søknader" in dashboard_response.text
    assert "Admin-kontoer" not in dashboard_response.text
    assert people_response.status_code == 200
    assert "Ny frivillig" in people_response.text


def test_dashboard_shows_april_toggle_only_for_it_leder() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    user.email = "it.leder@kvarteret.no"
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_mobile_card_april_state_service] = (
        lambda: FakeMobileCardAprilStateService()
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Mobil internkort-bilder" in response.text
    assert "Aktiver" in response.text


def test_dashboard_hides_april_toggle_for_other_admins() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_mobile_card_april_state_service] = (
        lambda: FakeMobileCardAprilStateService()
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Mobil internkort-bilder" not in response.text


def test_april_toggle_post_forbids_other_admins() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    april_service = FakeMobileCardAprilStateService()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    app.dependency_overrides[get_mobile_card_april_state_service] = lambda: april_service
    client = TestClient(app)

    response = client.post(
        "/mobile-card-april-state",
        data={"enabled": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert april_service.set_calls == []


def test_container_backed_auth_middleware_populates_current_user_and_pending_count() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    pending_service = FakePendingVolunteerApplicationsService()
    container.volunteer_applications_service = pending_service  # type: ignore[assignment]
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Admin-kontoer" in response.text
    assert "Søknader" in response.text
    assert ">3<" in response.text
    assert pending_service.calls == 1


def test_container_backed_auth_middleware_skips_pending_count_for_htmx_fragments() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    pending_service = FakePendingVolunteerApplicationsService()
    container.volunteer_applications_service = pending_service  # type: ignore[assignment]
    container.volunteers_service = FakeVolunteersService()  # type: ignore[assignment]
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/volunteers/list",
        headers={"HX-Request": "true"},
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert pending_service.calls == 0


def test_container_backed_auth_middleware_renders_impersonation_banner() -> None:
    impersonated_user = make_authenticated_user(UserRole.VOLUNTEER)
    admin_user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = ImpersonatedSessionStore(impersonated_user, admin_user)
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Impersonering aktiv" in response.text
    assert "Avslutt impersonering" in response.text


def test_stop_impersonation_restores_admin_session() -> None:
    impersonated_user = make_authenticated_user(UserRole.VOLUNTEER)
    admin_user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    session_store = ImpersonatedSessionStore(impersonated_user, admin_user)
    container.session_store = session_store
    app = create_app(container=container)
    client = TestClient(app)
    session_cookie = container.session_cookie_signer.sign_session_id("session-123")
    prime_csrf(
        client,
        cookies={container.settings.session_cookie_name: session_cookie},
    )

    response = client.post(
        "/impersonation/stop",
        headers=csrf_headers(client),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "kvarteret_session" in response.headers["set-cookie"]
    assert session_store.created_sessions == [
        {
            "auth_user_id": admin_user.auth_user_id,
            "user_account_id": admin_user.user_account_id,
            "impersonator_auth_user_id": None,
            "impersonator_user_account_id": None,
        }
    ]
    assert session_store.deleted_sessions == ["session-123"]


def test_logout_rejects_missing_csrf_when_session_cookie_is_present() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    app = create_app(container=container)
    client = TestClient(app)

    response = client.post(
        "/logout",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_logout_accepts_valid_csrf_token_when_session_cookie_is_present() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    app = create_app(container=container)
    client = TestClient(app)
    prime_csrf(
        client,
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    response = client.post(
        "/logout",
        headers=csrf_headers(client),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_protected_web_page_redirects_to_login_when_unauthenticated() -> None:
    client = TestClient(create_app())

    response = client.get("/volunteers", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_protected_htmx_fragment_redirects_to_login_when_unauthenticated() -> None:
    client = TestClient(create_app())

    response = client.get("/volunteers/list", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/login"
