import json

import httpx
import pytest

from app.config import Settings
from app.errors import NotConfiguredError
from app.exception_diagnostics import exception_diagnostics
from app.infrastructure.email.resend import ResendDeliveryError, ResendEmailSender


def sender(handler):
    return ResendEmailSender(
        Settings(_env_file=None, resend_api_key="test-secret"),
        transport=httpx.MockTransport(handler),
    )


async def send(adapter):
    await adapter.send_email(
        recipient_email="recipient@example.com",
        subject="Original subject",
        html_body="<p>Original copy</p>",
        idempotency_key="email-delivery/fixed",
    )


async def test_https_sender_preserves_copy_sender_and_idempotency_key():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "provider-id"})

    adapter = sender(handler)
    await send(adapter)
    await send(adapter)
    for request in requests:
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert request.headers["idempotency-key"] == "email-delivery/fixed"
        assert json.loads(request.content) == {
            "from": "Samfunnet i Bergen <hallaien@samfunnetibergen.no>",
            "to": ["recipient@example.com"],
            "subject": "Original subject",
            "html": "<p>Original copy</p>",
        }


@pytest.mark.parametrize(
    "status,retryable",
    [(429, True), (503, True), (401, False), (403, False), (422, False)],
)
async def test_http_failures_classified_without_provider_body(status, retryable):
    adapter = sender(
        lambda request: httpx.Response(
            status, json={"message": "private email, token=test-secret"}
        )
    )
    with pytest.raises(ResendDeliveryError) as raised:
        await send(adapter)
    error = raised.value
    assert error.http_status == status
    assert error.retryable is retryable
    assert "test-secret" not in str(error)
    assert "private" not in json.dumps(exception_diagnostics(error))


@pytest.mark.parametrize(
    "name,retryable",
    [("concurrent_idempotent_requests", True), ("invalid_idempotent_request", False)],
)
async def test_idempotency_conflict_requires_recovery_for_changed_payload(
    name, retryable
):
    with pytest.raises(ResendDeliveryError) as raised:
        await send(sender(lambda request: httpx.Response(409, json={"name": name})))
    assert raised.value.retryable is retryable


async def test_ambiguous_timeout_can_retry_with_same_key_and_safe_diagnostics():
    def handler(request):
        raise httpx.ReadTimeout("private email test-secret", request=request)

    with pytest.raises(ResendDeliveryError) as raised:
        await send(sender(handler))
    assert raised.value.retryable and raised.value.delivery_uncertain
    assert raised.value.__cause__ is None
    assert "test-secret" not in json.dumps(exception_diagnostics(raised.value))


async def test_malformed_success_does_not_mark_delivered():
    with pytest.raises(ResendDeliveryError) as raised:
        await send(sender(lambda request: httpx.Response(200, json={})))
    assert raised.value.delivery_uncertain


async def test_missing_key_never_contacts_provider():
    def handler(request):
        pytest.fail("must not contact provider without configuration")

    with pytest.raises(NotConfiguredError):
        await send(
            ResendEmailSender(
                Settings(_env_file=None), transport=httpx.MockTransport(handler)
            )
        )
    assert "test-secret" not in repr(
        Settings(_env_file=None, resend_api_key="test-secret")
    )
