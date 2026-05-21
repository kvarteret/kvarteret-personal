import json

from app.config import Settings
from app.domain.feedback.service import FeedbackSubmission, _create_linear_issue


def test_create_linear_issue_lets_linear_assign_triage_state_and_customer_request(monkeypatch) -> None:
    captured: list[dict[str, object]] = []
    responses = [
        b'{"data":{"issueCreate":{"success":true,'
        b'"issue":{"id":"issue-id","identifier":"DAK-123","url":"https://linear.app/kvarteret/issue/DAK-123/test"}}}}',
        b'{"data":{"customerUpsert":{"success":true,"customer":{"id":"customer-id"}}}}',
        b'{"data":{"customerNeedCreate":{"success":true,"need":{"id":"need-id"}}}}',
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
    assert captured[0]["authorization"] == "lin_api_example"

    customer_input = captured[1]["payload"]["variables"]["input"]
    assert customer_input == {
        "name": "System User <admin.user@example.test>",
        "externalId": "kvarteret-feedback-email:admin.user@example.test",
    }

    need_input = captured[2]["payload"]["variables"]["input"]
    assert need_input["issueId"] == "issue-id"
    assert need_input["customerId"] == "customer-id"
    assert "customerExternalId" not in need_input
    assert "Email: admin.user@example.test" in need_input["body"]
