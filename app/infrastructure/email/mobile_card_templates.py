from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True, slots=True)
class MobileCardEmail:
    subject: str
    html_body: str


class MobileCardEmailTemplateRendererProtocol(Protocol):
    def render_access_code_email(
        self, *, access_code: str, expires_in_minutes: int
    ) -> MobileCardEmail: ...


class MobileCardEmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or (
            Path(__file__).resolve().parents[2] / "templates" / "emails" / "compiled"
        )
        self._environment = Environment(
            loader=FileSystemLoader(str(resolved_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_access_code_email(
        self, *, access_code: str, expires_in_minutes: int
    ) -> MobileCardEmail:
        return MobileCardEmail(
            subject="Kvarteret Internkort is ready for you",
            html_body=self._render(
                "mobile_card_access_code.html",
                access_code=access_code,
                expires_in_minutes=expires_in_minutes,
            ),
        )

    def _render(self, template_name: str, **context: object) -> str:
        template = self._environment.get_template(template_name)
        return template.render(**context)
