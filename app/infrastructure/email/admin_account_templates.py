from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True, slots=True)
class AdminAccountEmail:
    subject: str
    html_body: str


class AdminAccountEmailTemplateRendererProtocol(Protocol):
    def render_onboarding_email(
        self,
        *,
        setup_url: str,
        display_name: str | None,
        username: str,
        role_name: str,
    ) -> AdminAccountEmail: ...


class AdminAccountEmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or (Path(__file__).resolve().parents[2] / "templates" / "emails" / "compiled")
        self._environment = Environment(
            loader=FileSystemLoader(str(resolved_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_onboarding_email(
        self,
        *,
        setup_url: str,
        display_name: str | None,
        username: str,
        role_name: str,
    ) -> AdminAccountEmail:
        return AdminAccountEmail(
            subject="Set up your Kvarteret admin account / Sett opp admin-kontoen din hos Kvarteret",
            html_body=self._render(
                "admin_account_onboarding.html",
                setup_url=setup_url,
                display_name=display_name,
                username=username,
                role_name=role_name,
            ),
        )

    def _render(self, template_name: str, **context: object) -> str:
        template = self._environment.get_template(template_name)
        return template.render(**context)
