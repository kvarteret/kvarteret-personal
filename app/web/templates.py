from fastapi.templating import Jinja2Templates

from app.web.i18n import get_template_gettext, get_template_ngettext


templates = Jinja2Templates(directory="app/templates")
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_callables(
    gettext=get_template_gettext,
    ngettext=get_template_ngettext,
    newstyle=True,
)
