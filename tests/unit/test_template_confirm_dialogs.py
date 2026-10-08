"""Destructive forms must confirm through htmx, not inline `onsubmit`.

The body boosts every form (`hx-boost:inherited`). htmx 4 issues the request
from its own submit listener without checking `defaultPrevented`, so an inline
`onsubmit="return confirm(...)"` that returns false still sends the request:
cancelling the dialog deleted the row anyway. `hx-confirm` runs inside htmx's
request pipeline and aborts correctly.
"""

import re
from pathlib import Path

TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "app" / "templates"
ONSUBMIT_CONFIRM = re.compile(r"onsubmit\s*=\s*\"[^\"]*confirm\(", re.IGNORECASE)


def test_no_template_confirms_through_onsubmit():
    offenders = [
        f"{path.relative_to(TEMPLATES_ROOT)}:{line_number}"
        for path in sorted(TEMPLATES_ROOT.rglob("*.html"))
        for line_number, line in enumerate(path.read_text().splitlines(), start=1)
        if ONSUBMIT_CONFIRM.search(line)
    ]

    assert offenders == [], (
        "Use hx-confirm instead of onsubmit confirm(): " + ", ".join(offenders)
    )
