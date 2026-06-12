"""Build an anonymized development seed from the production database.

For maintainers with production access. Produces ``seeds/dev-snapshot.sql``
(gitignored — distribute out-of-band; this is a public repository and even
pseudonymized role histories are volunteer data):

1. restores a data-only dump of production into a scratch database inside
   the dev compose Postgres (secret-bearing tables are never dumped),
2. rewrites every volunteer-identifying column with deterministic fakes,
3. **verifies** the rewrite — any surviving real-looking value aborts,
4. dumps the scratch database as the seed ``scripts/dev/bootstrap.py``
   prefers over the synthetic seed.

Usage (dev database must be up: ``make dev-up``):

    uv run python scripts/dev/make_anonymized_snapshot.py --from-dotenv
    uv run python scripts/dev/make_anonymized_snapshot.py --database-url postgresql://…
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = REPO_ROOT / "seeds"
SNAPSHOT_PATH = SEEDS_DIR / "dev-snapshot.sql"
SCRATCH_DB = "snapshot_scratch"
SCRATCH_URL = f"postgresql+asyncpg://postgres:postgres@localhost:55432/{SCRATCH_DB}"
COMPOSE = ["docker", "compose", "-f", str(REPO_ROOT / "docker-compose.dev.yml")]

# Never dumped from production: secrets, sessions, throttles, and the
# audit log (its payloads embed applicant emails).
EXCLUDED_TABLES = [
    "alembic_version",
    "web_sessions",
    "integration_tokens",
    "mobile_card_access_codes",
    "rate_limits",
    "domain_events",
    "volunteer_photos",
]

FIRST_NAMES = (
    "Ada,Birk,Clara,Didrik,Eira,Frida,Gustav,Hedda,Iver,Jenny,Kasper,Live,"
    "Mats,Nora,Oskar,Pernille,Randi,Ronja,Sander,Tuva,Ulrik,Vilde,William,Ylva"
)
LAST_NAMES = (
    "Andersen,Berg,Christiansen,Dahl,Eriksen,Fjeld,Gundersen,Haugen,Iversen,"
    "Johansen,Knutsen,Lie,Moen,Nilsen,Olsen,Pedersen,Rasmussen,Solberg,Tangen,Vik"
)

ANONYMIZE_SQL = f"""
WITH names AS (
    SELECT string_to_array('{FIRST_NAMES}', ',') AS first_names,
           string_to_array('{LAST_NAMES}', ',') AS last_names
)
UPDATE volunteer_records v SET
    first_name = (SELECT first_names[1 + (v.id % 24)] FROM names),
    last_name = (SELECT last_names[1 + ((v.id / 24) % 20)] FROM names),
    email = 'volunteer.' || v.id || '@example.dev',
    phone = '4' || lpad(((v.id * 7919) % 10000000)::text, 7, '0'),
    birth_date = DATE '1996-01-01' + ((v.id * 37) % 3650)::int,
    street_address = 'Devgate ' || (1 + v.id % 90),
    postal_code = (ARRAY['5006','5007','5011','5014','5015','5018','5020'])[1 + v.id % 7];

UPDATE volunteer_next_of_kin SET
    name = 'Pårørende ' || id,
    phone = '4' || lpad(((id * 104729) % 10000000)::text, 7, '0');

UPDATE volunteer_cards SET card_number = 'DEV-' || id;

UPDATE volunteer_application_invites SET
    email = 'applicant.' || id || '@example.dev',
    token = 'dev-token-' || id;

WITH names AS (
    SELECT string_to_array('{FIRST_NAMES}', ',') AS first_names,
           string_to_array('{LAST_NAMES}', ',') AS last_names
)
UPDATE volunteer_application_submissions s SET
    first_name = (SELECT first_names[1 + (s.id % 24)] FROM names),
    last_name = (SELECT last_names[1 + ((s.id / 24) % 20)] FROM names),
    email = 'applicant.' || s.invite_id || '@example.dev',
    phone = '4' || lpad(((s.id * 6271) % 10000000)::text, 7, '0'),
    birth_date = NULL,
    street_address = 'Devgate ' || (1 + s.id % 90),
    postal_code = '5015',
    studiested = 'Universitetet i Bergen',
    bakgrunn = NULL,
    internkortaccesstoken = NULL,
    photo_sha1 = NULL,
    photo_filetype = NULL;

UPDATE volunteer_application_group_members SET
    applicant_email = CASE
        WHEN invite_id IS NOT NULL THEN 'applicant.' || invite_id || '@example.dev'
        ELSE 'applicant.m' || id || '@example.dev'
    END;

UPDATE user_accounts SET
    username = 'admin' || id,
    email = 'admin' || id || '@kvarteret.dev',
    display_name = 'Admin ' || id;
"""

VERIFICATION_CHECKS: list[tuple[str, str]] = [
    ("volunteer emails", "SELECT count(*) FROM volunteer_records WHERE email NOT LIKE '%@example.dev'"),
    ("volunteer names", f"SELECT count(*) FROM volunteer_records WHERE first_name <> ALL(string_to_array('{FIRST_NAMES}', ','))"),
    ("volunteer phones", "SELECT count(*) FROM volunteer_records WHERE phone IS NOT NULL AND phone !~ '^4[0-9]{7}$'"),
    ("volunteer addresses", "SELECT count(*) FROM volunteer_records WHERE street_address IS NOT NULL AND street_address NOT LIKE 'Devgate %'"),
    ("next of kin", "SELECT count(*) FROM volunteer_next_of_kin WHERE name NOT LIKE 'Pårørende %'"),
    ("card numbers", "SELECT count(*) FROM volunteer_cards WHERE card_number NOT LIKE 'DEV-%'"),
    ("invite emails", "SELECT count(*) FROM volunteer_application_invites WHERE email NOT LIKE '%@example.dev'"),
    ("invite tokens", "SELECT count(*) FROM volunteer_application_invites WHERE token NOT LIKE 'dev-token-%'"),
    ("submission emails", "SELECT count(*) FROM volunteer_application_submissions WHERE email NOT LIKE '%@example.dev'"),
    ("submission free text", "SELECT count(*) FROM volunteer_application_submissions WHERE bakgrunn IS NOT NULL OR internkortaccesstoken IS NOT NULL"),
    ("group member emails", "SELECT count(*) FROM volunteer_application_group_members WHERE applicant_email NOT LIKE '%@example.dev'"),
    ("admin emails", "SELECT count(*) FROM user_accounts WHERE email NOT LIKE '%@kvarteret.dev'"),
    ("photos excluded", "SELECT count(*) FROM volunteer_photos"),
    ("sessions excluded", "SELECT count(*) FROM web_sessions"),
    ("tokens excluded", "SELECT count(*) FROM integration_tokens"),
    ("access codes excluded", "SELECT count(*) FROM mobile_card_access_codes"),
    ("rate limits excluded", "SELECT count(*) FROM rate_limits"),
    ("audit log excluded", "SELECT count(*) FROM domain_events"),
]


def to_libpq(url: str) -> str:
    cleaned = url.replace("postgresql+asyncpg://", "postgresql://")
    # pg_dump needs the session pooler, not the transaction pooler,
    # and libpq spells the TLS parameter sslmode, not asyncpg's ssl.
    cleaned = cleaned.replace(":6543/", ":5432/")
    return re.sub(r"([?&])ssl=[^&]*", r"\1sslmode=require", cleaned)


def scratch_psql(*args: str, **kwargs):
    return subprocess.run(
        [*COMPOSE, "exec", "-T", "db", *args], check=True, **kwargs
    )


def prepare_scratch() -> None:
    scratch_psql("psql", "-q", "-U", "postgres", "-d", "postgres", "-c",
                 f'DROP DATABASE IF EXISTS {SCRATCH_DB}')
    scratch_psql("psql", "-q", "-U", "postgres", "-d", "postgres", "-c",
                 f'CREATE DATABASE {SCRATCH_DB}')
    scratch_psql("psql", "-q", "-U", "postgres", "-d", SCRATCH_DB, "-v", "ON_ERROR_STOP=1",
                 "-f", "/docker-entrypoint-initdb.d/10-supabase-stubs.sql")
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": SCRATCH_URL},
        check=True,
    )


def restore_production_data(source_url: str) -> None:
    excludes = " ".join(f"-T public.{table}" for table in EXCLUDED_TABLES)
    command = (
        f'pg_dump "$SOURCE_URL" --data-only --schema=public --no-owner '
        f"--no-privileges --disable-triggers {excludes} "
        f"| psql -q -v ON_ERROR_STOP=1 -U postgres -d {SCRATCH_DB}"
    )
    subprocess.run(
        [*COMPOSE, "exec", "-T", "-e", f"SOURCE_URL={to_libpq(source_url)}",
         "db", "bash", "-ceuo", "pipefail", command],
        check=True,
    )


async def anonymize_and_verify() -> None:
    engine = create_async_engine(SCRATCH_URL)
    try:
        async with engine.begin() as conn:
            for statement in ANONYMIZE_SQL.split(";"):
                if statement.strip():
                    await conn.execute(text(statement))
        async with engine.connect() as conn:
            failures = []
            for label, query in VERIFICATION_CHECKS:
                count = (await conn.execute(text(query))).scalar_one()
                if count:
                    failures.append(f"  {label}: {count} rows still look real")
            volunteers = (
                await conn.execute(text("SELECT count(*) FROM volunteer_records"))
            ).scalar_one()
            if failures:
                raise SystemExit(
                    "Anonymization verification FAILED — snapshot not written:\n"
                    + "\n".join(failures)
                )
            print(f"Verification passed: {volunteers} volunteers anonymized.")
    finally:
        await engine.dispose()


def dump_snapshot() -> None:
    SEEDS_DIR.mkdir(exist_ok=True)
    header = (
        f"-- Anonymized development seed generated {datetime.now(UTC):%Y-%m-%d %H:%M}Z\n"
        "-- by scripts/dev/make_anonymized_snapshot.py. Volunteer-identifying\n"
        "-- data is synthetic; structural data (groups, courses, roles,\n"
        "-- assignments) mirrors production. Do not commit: distribute\n"
        "-- out-of-band to developers.\n"
    )
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "db", "pg_dump", "-U", "postgres", "-d", SCRATCH_DB,
         "--data-only", "--schema=public", "--no-owner", "--no-privileges",
         "--disable-triggers", "-T", "public.alembic_version"],
        check=True,
        capture_output=True,
        text=True,
    )
    SNAPSHOT_PATH.write_text(header + result.stdout, encoding="utf-8")
    print(f"Wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)} "
          f"({SNAPSHOT_PATH.stat().st_size // 1024} KiB).")


def drop_scratch() -> None:
    scratch_psql("psql", "-q", "-U", "postgres", "-d", "postgres", "-c",
                 f'DROP DATABASE IF EXISTS {SCRATCH_DB}')


def resolve_source_url(args: argparse.Namespace) -> str:
    if args.database_url:
        return args.database_url
    if args.from_dotenv:
        for line in (REPO_ROOT / ".env").read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
        raise SystemExit(".env has no DATABASE_URL.")
    raise SystemExit("Provide --database-url or --from-dotenv.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Production database URL (read-only use).")
    parser.add_argument("--from-dotenv", action="store_true",
                        help="Read DATABASE_URL from .env.")
    args = parser.parse_args()
    source_url = resolve_source_url(args)

    print("Preparing scratch database …")
    prepare_scratch()
    try:
        print("Restoring production data (secret tables excluded) …")
        restore_production_data(source_url)
        print("Anonymizing …")
        asyncio.run(anonymize_and_verify())
        dump_snapshot()
    finally:
        drop_scratch()
    print("Load it with: make dev-reset")


if __name__ == "__main__":
    sys.exit(main())
