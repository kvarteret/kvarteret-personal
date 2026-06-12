from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.tables import public_metadata

DEFAULT_IGNORED_TABLES = frozenset({"alembic_version"})


def _sorted_names(names: Iterable[str]) -> list[str]:
    return sorted(set(names))


async def collect_database_schema(schema: str) -> dict[str, set[str]]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required.")

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_inspect_database_schema, schema)
    finally:
        await engine.dispose()


def _inspect_database_schema(connection, schema: str) -> dict[str, set[str]]:
    inspector = inspect(connection)
    return {
        table_name: {
            column["name"] for column in inspector.get_columns(table_name, schema=schema)
        }
        for table_name in inspector.get_table_names(schema=schema)
    }


def collect_metadata_schema(schema: str) -> dict[str, set[str]]:
    return {
        table.name: {column.name for column in table.columns}
        for table in public_metadata.tables.values()
        if table.schema == schema
    }


def render_drift(
    *,
    database_schema: dict[str, set[str]],
    metadata_schema: dict[str, set[str]],
    ignored_tables: set[str],
) -> list[str]:
    database_tables = set(database_schema) - ignored_tables
    metadata_tables = set(metadata_schema) - ignored_tables
    lines: list[str] = []

    extra_tables = database_tables - metadata_tables
    missing_tables = metadata_tables - database_tables
    if extra_tables:
        lines.append("Extra database tables:")
        lines.extend(f"  + {table}" for table in _sorted_names(extra_tables))
    if missing_tables:
        lines.append("Missing database tables:")
        lines.extend(f"  - {table}" for table in _sorted_names(missing_tables))

    for table in _sorted_names(database_tables & metadata_tables):
        database_columns = database_schema[table]
        metadata_columns = metadata_schema[table]
        extra_columns = database_columns - metadata_columns
        missing_columns = metadata_columns - database_columns
        if not extra_columns and not missing_columns:
            continue
        lines.append(f"Column drift in {table}:")
        lines.extend(f"  + {column}" for column in _sorted_names(extra_columns))
        lines.extend(f"  - {column}" for column in _sorted_names(missing_columns))

    return lines


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare reflected public database tables against SQLAlchemy metadata."
    )
    parser.add_argument("--schema", default="public")
    parser.add_argument(
        "--ignore-table",
        action="append",
        default=[],
        help="Table name to ignore. Can be passed multiple times.",
    )
    args = parser.parse_args()

    ignored_tables = set(DEFAULT_IGNORED_TABLES) | set(args.ignore_table)
    database_schema = await collect_database_schema(args.schema)
    metadata_schema = collect_metadata_schema(args.schema)
    drift = render_drift(
        database_schema=database_schema,
        metadata_schema=metadata_schema,
        ignored_tables=ignored_tables,
    )

    if drift:
        print("Schema drift detected.")
        print("\n".join(drift))
        return 1

    print("Schema matches SQLAlchemy metadata.")
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
