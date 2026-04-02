from __future__ import annotations

import smtplib
from asyncio import to_thread
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Settings
from app.errors import NotConfiguredError
from app.infrastructure.email.protocols import EmailSenderProtocol


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(self, *, recipient_email: str, subject: str, html_body: str) -> None:
        if not self._is_configured():
            raise NotConfiguredError("SMTP email is not configured.")
        await to_thread(
            _send_via_smtp,
            server=self.settings.smtp_server or "",
            port=self.settings.smtp_port,
            sender_name=self.settings.smtp_sender_name or "",
            sender_email=self.settings.smtp_sender_email or "",
            account=self.settings.smtp_account or "",
            password=self.settings.smtp_password or "",
            recipient_email=recipient_email,
            subject=subject,
            html_body=html_body,
            use_starttls=self.settings.smtp_use_starttls,
        )

    def _is_configured(self) -> bool:
        return all(
            [
                self.settings.smtp_server,
                self.settings.smtp_sender_name,
                self.settings.smtp_sender_email,
                self.settings.smtp_account,
                self.settings.smtp_password,
            ]
        )


def _send_via_smtp(
    *,
    server: str,
    port: int,
    sender_name: str,
    sender_email: str,
    account: str,
    password: str,
    recipient_email: str,
    subject: str,
    html_body: str,
    use_starttls: bool,
) -> None:
    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(html_body, subtype="html")

    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.ehlo()
        if use_starttls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(account, password)
        smtp.send_message(message)
