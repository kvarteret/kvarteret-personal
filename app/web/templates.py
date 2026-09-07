from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.web.i18n import get_template_gettext, get_template_ngettext


OSLO_TIMEZONE = ZoneInfo("Europe/Oslo")


def format_datetime_oslo(value: datetime | None) -> str:
    """Format an instant for Norwegian admin-facing pages."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(OSLO_TIMEZONE).strftime("%d.%m.%Y %H:%M")


templates = Jinja2Templates(directory="app/templates")
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_callables(
    gettext=get_template_gettext,
    ngettext=get_template_ngettext,
    newstyle=True,
)
templates.env.globals["format_datetime_oslo"] = format_datetime_oslo
