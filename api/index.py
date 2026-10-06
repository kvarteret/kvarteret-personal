import os

def create_entrypoint():
    if os.environ.get('VERCEL_ENV') != 'preview' or os.environ.get('APP_ENV'):
        from app.main import create_app

        return create_app()

    # This trial branch contains CLI tooling. Its unconfigured preview must not
    # load production credentials or weaken the application's startup checks.
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/', response_class=HTMLResponse)
    def trial_preview():
        return HTMLResponse('''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin account migration trial</title>
<style>
body { margin:0; background:#f5f4ef; color:#18251e;
font:17px/1.65 system-ui,sans-serif; }
main { max-width:720px; margin:7vh auto; padding:32px; }
h1 { font-size:clamp(30px,5vw,44px); line-height:1.15; }
.tag { font-size:13px; text-transform:uppercase; letter-spacing:.12em; }
section { background:white; padding:24px; border-radius:0; margin:24px 0; }
code { overflow-wrap:anywhere; font-size:14px; }
a { color:#225d42; }
</style></head><body><main>
<p class="tag">Draft PR · Trial planner</p>
<h1>Individual admin accounts from volunteer profiles</h1>
<p>This trial produces a private migration plan for review. Run the planner
from a local checkout using a private inventory and mapping decisions.</p>
<section><h2>Included in the plan</h2><ul>
<li>Connect shared group accounts to one or several volunteers.</li>
<li>Combine a person's source accounts while preserving access grants.</li>
<li>Propose Admin access for current Administrasjonen and Hovedstyret members.</li>
<li>Record removals and flag identities, emails, and permissions for review.</li>
</ul></section>
<section><h2>Run the trial locally</h2>
<p><code>uv run python scripts/plan_admin_volunteer_migration.py --help</code></p>
<p>Keep inventories, mapping decisions, and generated plans outside Git
checkouts. See the migration guide in the PR for the input format.</p></section>
<p>This preview displays no personal data. The trial has no apply mode and
does not create accounts, grant production access, or send invitations.</p>
<p>The full Personal application is unavailable on this preview because its
database and authentication environment have not been configured.</p>
<p><a href="https://github.com/kvarteret/kvarteret-personal/pull/76">Review draft PR #76</a></p>
</main></body></html>''')
    return app


app = create_entrypoint()
