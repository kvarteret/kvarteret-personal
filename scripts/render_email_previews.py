from __future__ import annotations

# ruff: noqa: E402

from pathlib import Path
from shutil import rmtree
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.email_template_previews import EmailPreview, build_previews

PREVIEWS_DIR = PROJECT_ROOT / "app" / "templates" / "emails" / "previews"


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
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700&amp;family=Fraunces:wght@650;700&amp;display=swap">
    <style>
      body {{
        margin: 0;
        padding: 40px 24px;
        background: #faf7f2;
        color: #26211e;
        font-family: 'DM Sans', Helvetica, Arial, sans-serif;
      }}
      main {{
        margin: 0 auto;
        max-width: 720px;
      }}
      h1 {{
        margin: 0 0 24px;
        font-size: 40px;
        line-height: 1.1;
        font-family: Fraunces, Georgia, 'Times New Roman', serif;
      }}
      ul {{
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 16px;
      }}
      .card {{
        border-left: 6px solid #db242a;
        background: #fff0d9;
        padding: 20px 22px;
      }}
      a {{
        color: #26211e;
        font-size: 22px;
        font-weight: 700;
        text-decoration: none;
      }}
      p {{
        margin: 10px 0 0;
        color: #6f655e;
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
