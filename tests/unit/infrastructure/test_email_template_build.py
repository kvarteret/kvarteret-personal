from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, meta

from app.infrastructure.email.admin_account_templates import (
    AdminAccountEmailTemplateRenderer,
)
from app.infrastructure.email.applicant_templates import ApplicantEmailTemplateRenderer


@pytest.mark.parametrize(
    "name,variables",
    [
        ("applicant_application_received", set()),
        ("applicant_invitation", {"invitation_url"}),
        ("applicant_profile_completion", {"invitation_url"}),
        ("applicant_friend_invitation", {"invitation_url", "inviter_name"}),
        (
            "admin_account_onboarding",
            {"setup_url", "display_name", "username", "role_name"},
        ),
        ("mobile_card_access_code", {"access_code", "expires_in_minutes"}),
        ("password_reset", {"setup_url"}),
    ],
)
def test_react_build_preserves_python_template_variables(name, variables):
    directory = Path(__file__).resolve().parents[3] / "app/templates/emails/compiled"
    html = (directory / f"{name}.html").read_text()
    assert meta.find_undeclared_variables(Environment().parse(html)) == variables
    assert "__EMAIL_PROP_" not in html


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


def test_react_build_keeps_runtime_values_escaped_and_links_intact():
    url = "https://example.test/apply/token?first=1&second=2"
    email = ApplicantEmailTemplateRenderer().render_friend_invitation_email(
        invitation_url=url, inviter_name="<script>alert(1)</script>"
    )
    assert "<script>" not in email.html_body
    assert "&lt;script&gt;" in email.html_body
    links = Links()
    links.feed(email.html_body)
    assert links.hrefs == [url, url]


@pytest.mark.parametrize("display_name", [None, "", "<script>Alex</script>"])
def test_react_build_preserves_optional_admin_greeting(display_name):
    email = AdminAccountEmailTemplateRenderer().render_onboarding_email(
        setup_url="https://example.test/setup",
        display_name=display_name,
        username="alex",
        role_name="Admin",
    )
    assert "<script>" not in email.html_body
    if display_name:
        assert "Hei &lt;script&gt;Alex&lt;/script&gt;," in email.html_body
    else:
        assert "Hei," in email.html_body
