from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.email.applicant_templates import (
    ApplicantEmailTemplateRenderer,
)
from app.infrastructure.email.admin_account_templates import (
    AdminAccountEmailTemplateRenderer,
)
from app.infrastructure.email.mobile_card_templates import (
    MobileCardEmailTemplateRenderer,
)


@dataclass(frozen=True, slots=True)
class EmailPreview:
    slug: str
    title: str
    subject: str
    html_body: str


PREVIEWS_DIR = PROJECT_ROOT / "app" / "templates" / "emails" / "previews"


def build_previews() -> list[EmailPreview]:
    applicant_renderer = ApplicantEmailTemplateRenderer()
    admin_account_renderer = AdminAccountEmailTemplateRenderer()
    mobile_card_renderer = MobileCardEmailTemplateRenderer()

    applicant_invitation_email = applicant_renderer.render_invitation_email(
        invitation_url="https://personal.kvarteret.no/apply/invite-token-preview",
    )
    applicant_profile_email = applicant_renderer.render_profile_completion_email(
        invitation_url="https://personal.kvarteret.no/apply/profile-token-preview",
    )
    mobile_card_email = mobile_card_renderer.render_access_code_email(
        access_code="483921",
        expires_in_minutes=10,
    )
    admin_account_email = admin_account_renderer.render_onboarding_email(
        setup_url="https://personal.kvarteret.no/set-password#access_token=preview-token",
        display_name="New Admin",
        username="new.admin",
        role_name="Admin",
    )

    return [
        EmailPreview(
            slug="applicant_invitation",
            title="Applicant Invitation",
            subject=applicant_invitation_email.subject,
            html_body=applicant_invitation_email.html_body,
        ),
        EmailPreview(
            slug="applicant_profile_completion",
            title="Applicant Profile Completion",
            subject=applicant_profile_email.subject,
            html_body=applicant_profile_email.html_body,
        ),
        EmailPreview(
            slug="admin_account_onboarding",
            title="Admin Account Onboarding",
            subject=admin_account_email.subject,
            html_body=admin_account_email.html_body,
        ),
        EmailPreview(
            slug="mobile_card_access_code",
            title="Mobile Card Access Code",
            subject=mobile_card_email.subject,
            html_body=mobile_card_email.html_body,
        ),
    ]


def write_previews(previews: list[EmailPreview]) -> None:
    if PREVIEWS_DIR.exists():
        rmtree(PREVIEWS_DIR)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    for preview in previews:
        preview_path = PREVIEWS_DIR / f"{preview.slug}.html"
        preview_path.write_text(preview.html_body, encoding="utf-8")

    index = _build_index(previews)
    (PREVIEWS_DIR / "index.html").write_text(index, encoding="utf-8")


def _build_index(previews: list[EmailPreview]) -> str:
    cards = "\n".join(
        (
            '      <li class="card">'
            f'<a href="{preview.slug}.html">{preview.title}</a>'
            f"<p>{preview.subject}</p>"
            "</li>"
        )
        for preview in previews
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Email Previews</title>
    <style>
      body {{
        margin: 0;
        padding: 40px 24px;
        background: #ffffff;
        color: #111111;
        font-family: Helvetica, Arial, sans-serif;
      }}
      main {{
        margin: 0 auto;
        max-width: 720px;
      }}
      h1 {{
        margin: 0 0 24px;
        font-size: 40px;
        line-height: 1.1;
      }}
      ul {{
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 16px;
      }}
      .card {{
        border-left: 8px solid #f54b4b;
        background: #ffffff;
        padding: 20px 22px;
      }}
      a {{
        color: #111111;
        font-size: 22px;
        font-weight: 700;
        text-decoration: none;
      }}
      p {{
        margin: 10px 0 0;
        color: #555555;
        font-size: 15px;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Email Previews</h1>
      <ul>
{cards}
      </ul>
    </main>
  </body>
</html>
"""


if __name__ == "__main__":
    write_previews(build_previews())
