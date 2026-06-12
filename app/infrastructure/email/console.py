"""Development-only email sender.

Logs every email and writes the HTML body to ``.devdata/outbox/`` so
apply links and access codes can be opened locally. Selected by
``app/runtime.py`` only in development when SMTP is not configured.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_HREF_PATTERN = re.compile(r'href="([^"]+)"')


class ConsoleEmailSender:
    def __init__(self, outbox_dir: str | Path = ".devdata/outbox") -> None:
        self.outbox_dir = Path(outbox_dir)

    async def send_email(
        self, *, recipient_email: str, subject: str, html_body: str
    ) -> None:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(subject)}.html"
        path = self.outbox_dir / filename
        path.write_text(html_body, encoding="utf-8")
        links = _HREF_PATTERN.findall(html_body)
        logger.info(
            "DEV EMAIL to=%s subject=%r saved=%s links=%s",
            recipient_email,
            subject,
            path,
            links or "-",
        )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "email"
