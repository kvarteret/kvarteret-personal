from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.main import create_app
from scripts.export_openapi import build_openapi_schema


ROOT = Path(__file__).resolve().parents[2]


def test_openapi_contains_stable_operation_ids() -> None:
    schema = create_app().openapi()
    operations = {
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if "operationId" in operation
    }

    assert {
        "getHealth",
        "getNowPlaying",
        "requestMobileCardAccessCode",
        "createMobileCardSession",
        "getCurrentMobileCard",
        "logMobileCardSessionLogoutEvent",
        "createPublicVolunteerProspect",
    }.issubset(operations)


def test_volunteer_prospect_contract_documents_security_controls() -> None:
    operation = create_app().openapi()["paths"][
        "/api/v1/volunteer-prospects"
    ]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert request_schema["properties"]["full_name"]["maxLength"] == 201
    assert request_schema["properties"]["friend_emails"]["anyOf"][0][
        "maxItems"
    ] == 2
    assert parameters["X-Kvarteret-Idempotency-Key"]["schema"]["format"] == "uuid"
    assert parameters["X-Kvarteret-Client-Key"]["schema"]["pattern"]
    assert {"413", "422", "429"}.issubset(operation["responses"])


def test_exported_openapi_schema_is_current() -> None:
    exported_path = ROOT / "openapi.json"
    assert exported_path.exists()
    exported = json.loads(exported_path.read_text())
    assert exported == build_openapi_schema()


def test_openapi_export_check_mode_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
