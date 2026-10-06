import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from app.middleware.canonical_web import CanonicalWebMiddleware


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(CanonicalWebMiddleware)

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'HEAD'])
    def page(path: str):
        return HTMLResponse('page')

    return TestClient(app, base_url='https://personal.kvarteret.no', follow_redirects=False)


def test_html_navigation_redirects_with_path_and_query(client):
    response = client.get('/login?next=%2Fgroups', headers={'Accept': 'text/html', 'Sec-Fetch-Dest': 'document'})
    assert response.status_code == 307
    assert response.headers['location'] == 'https://personal.samfunnetibergen.no/login?next=%2Fgroups'
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('path', ['/api/v1/mobile-card/session', '/api/now-playing', '/media/photos/example.jpg', '/images/10', '/static/output.css', '/internal/jobs', '/docs', '/redoc'])
def test_dependent_endpoints_never_redirect(client, path):
    assert client.get(path, headers={'Accept': 'text/html'}).status_code == 200


@pytest.mark.parametrize('headers', [
    {'Accept': 'application/json'},
    {'Accept': '*/*'},
    {'Accept': 'text/html', 'Authorization': 'Bearer example'},
    {'Accept': 'text/html', 'HX-Request': 'true'},
    {'Accept': 'text/html', 'Sec-Fetch-Dest': 'image'},
])
def test_non_navigation_requests_do_not_redirect(client, headers):
    assert client.get('/groups', headers=headers).status_code == 200


@pytest.mark.parametrize('method', ['POST', 'HEAD'])
def test_other_methods_do_not_redirect(client, method):
    assert client.request(method, '/login/app', headers={'Accept': 'text/html'}).status_code == 200


def test_canonical_hostname_does_not_redirect(client):
    assert client.get('https://personal.samfunnetibergen.no/login', headers={'Accept': 'text/html'}).status_code == 200
