from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True, slots=True)
class ApplicantEmail:
    subject: str
    html_body: str


class ApplicantEmailTemplateRendererProtocol(Protocol):
    def render_invitation_email(self, *, invitation_url: str) -> ApplicantEmail: ...

    def render_profile_completion_email(self, *, invitation_url: str) -> ApplicantEmail: ...


class ApplicantEmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or (Path(__file__).resolve().parents[2] / "templates" / "emails" / "compiled")
        self._environment = Environment(
            loader=FileSystemLoader(str(resolved_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_invitation_email(self, *, invitation_url: str) -> ApplicantEmail:
        return ApplicantEmail(
            subject="Complete your Kvarteret registration / Fullfør registreringen din hos Kvarteret",
            html_body=self._render(
                "applicant_invitation.html",
                invitation_url=invitation_url,
            ),
        )

    def render_profile_completion_email(self, *, invitation_url: str) -> ApplicantEmail:
        return ApplicantEmail(
            subject="Complete your Kvarteret profile / Fullfør Kvarteret-profilen din",
            html_body=self._render(
                "applicant_profile_completion.html",
                invitation_url=invitation_url,
            ),
        )

    def _render(self, template_name: str, **context: object) -> str:
        template = self._environment.get_template(template_name)
        return template.render(**context)
