import json

import pytest

from app.config import Settings
from app.db.rate_limit import InMemoryRateLimiter
from app.domain.feedback.service import (
    FeedbackRateLimitedError,
    FeedbackService,
    FeedbackSubmission,
    _create_linear_issue,
)


def test_create_linear_issue_lets_linear_assign_triage_state_and_includes_email(monkeypatch) -> None:
    captured: list[dict[str, object]] = []
    responses = [
        b'{"data":{"issueCreate":{"success":true,'
        b'"issue":{"id":"issue-id","identifier":"DAK-123","url":"https://linear.app/kvarteret/issue/DAK-123/test"}}}}',
    ]

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    def fake_urlopen(req, timeout: int):
        captured.append(
            {
                "timeout": timeout,
                "payload": json.loads(req.data.decode("utf-8")),
                "authorization": req.headers["Authorization"],
            }
        )
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr("app.domain.feedback.service.urllib_request.urlopen", fake_urlopen)

    _create_linear_issue(
        FeedbackSubmission(
            category="forslag",
            feedback_type=None,
            name="System User",
            email="admin.user@example.test",
            message="Legg til bedre sok.",
            page="/volunteers",
            platform="web",
            user_id=None,
            submitted_at="21.05.2026 15:20",
            source="personalplattformen",
        ),
        Settings(
            linear_api_key="lin_api_example",
            linear_team_id="team-id",
            linear_project_id_personal="project-id",
            linear_state_id_triage="triage-state-id",
        ),
    )

    issue_input = captured[0]["payload"]["variables"]["input"]
    assert issue_input["teamId"] == "team-id"
    assert issue_input["projectId"] == "project-id"
    assert "stateId" not in issue_input
    assert "E-post:** admin.user@example.test" in issue_input["description"]
    assert captured[0]["authorization"] == "lin_api_example"
    assert len(captured) == 1


def _settings_for_rate_limit_tests(**overrides) -> Settings:
    return Settings(
        linear_api_key="lin_api_example",
        linear_team_id="team-id",
        linear_project_id_internbevis="project-id",
        feedback_submission_limit=2,
        feedback_submission_window_seconds=600,
        **overrides,
    )


@pytest.mark.asyncio
async def test_submit_feedback_raises_after_limit_exceeded_for_same_source_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.domain.feedback.service._create_linear_issue", lambda *a, **k: None
    )
    service = FeedbackService(
        _settings_for_rate_limit_tests(), rate_limiter=InMemoryRateLimiter()
    )

    for _ in range(2):
        await service.submit_feedback(
            name=None,
            email=None,
            message="Hei",
            page="/home",
            source="internbevis-rn",
            source_key="1.2.3.4",
        )

    with pytest.raises(FeedbackRateLimitedError):
        await service.submit_feedback(
            name=None,
            email=None,
            message="Hei igjen",
            page="/home",
            source="internbevis-rn",
            source_key="1.2.3.4",
        )


@pytest.mark.asyncio
async def test_submit_feedback_rate_limit_is_scoped_per_source_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.domain.feedback.service._create_linear_issue", lambda *a, **k: None
    )
    service = FeedbackService(
        _settings_for_rate_limit_tests(), rate_limiter=InMemoryRateLimiter()
    )

    for _ in range(2):
        await service.submit_feedback(
            name=None,
            email=None,
            message="Hei",
            page="/home",
            source="internbevis-rn",
            source_key="1.2.3.4",
        )

    # A different source key has its own counter and is unaffected.
    await service.submit_feedback(
        name=None,
        email=None,
        message="Hei fra en annen IP",
        page="/home",
        source="internbevis-rn",
        source_key="5.6.7.8",
    )


@pytest.mark.asyncio
async def test_submit_feedback_without_source_key_uses_a_shared_fallback_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.domain.feedback.service._create_linear_issue", lambda *a, **k: None
    )
    service = FeedbackService(
        _settings_for_rate_limit_tests(), rate_limiter=InMemoryRateLimiter()
    )

    for _ in range(2):
        await service.submit_feedback(
            name=None,
            email=None,
            message="Hei",
            page="/home",
            source="internbevis-rn",
            source_key=None,
        )

    with pytest.raises(FeedbackRateLimitedError):
        await service.submit_feedback(
            name=None,
            email=None,
            message="Hei igjen",
            page="/home",
            source="internbevis-rn",
            source_key=None,
        )
