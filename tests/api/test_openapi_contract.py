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
        "listEvents",
        "getEvent",
        "getEventTaxonomy",
        "requestMobileCardAccessCode",
        "createMobileCardSession",
        "getCurrentMobileCard",
        "logMobileCardSessionLogoutEvent",
        "createPublicVolunteerProspect",
        "legacyRequestMobileCardAccessTokenOnEmail",
        "legacyGetMobileCardInformation",
    }.issubset(operations)
    assert schema["paths"]["/api/v1/events"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/EventList")
    assert (
        schema["paths"]["/api/DigitalInternkort/GetInternkortInformation"]["post"][
            "deprecated"
        ]
        is True
    )


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
