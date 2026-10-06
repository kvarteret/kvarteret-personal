import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


def test_unconfigured_vercel_preview_serves_trial_without_loading_app(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    monkeypatch.delenv('APP_ENV', raising=False)
    spec = importlib.util.spec_from_file_location('trial_entrypoint', Path('api/index.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert 'Trial planner' in response.text
        assert 'Hovedstyret' in response.text
        assert 'no apply mode' in response.text
        assert client.get('/docs').status_code == 404
