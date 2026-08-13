from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True, slots=True)
class PasswordResetEmail:
    subject: str
    html_body: str


class PasswordResetEmailTemplateRendererProtocol(Protocol):
    def render_password_reset_email(self, *, setup_url: str) -> PasswordResetEmail: ...


class PasswordResetEmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or (
            Path(__file__).resolve().parents[2] / "templates" / "emails" / "compiled"
        )
        self._environment = Environment(
            loader=FileSystemLoader(str(resolved_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_password_reset_email(self, *, setup_url: str) -> PasswordResetEmail:
        template = self._environment.get_template("password_reset.html")
        return PasswordResetEmail(
            subject="Tilbakestill passordet ditt hos Kvarteret",
            html_body=template.render(setup_url=setup_url),
        )
