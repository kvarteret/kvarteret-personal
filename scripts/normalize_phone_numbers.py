from __future__ import annotations

import argparse
import asyncio
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.db.session import build_database_runtime
from app.services.phone_numbers import analyze_phone_number, is_obviously_false_phone_number

TABLES = (
    ("personal", "id", "telefon"),
    ("paarorende", "id", "telefon"),
    ("nytt_personal", "id", "telefon"),
    ("aspnetusers", "id", "phonenumber"),
)
NON_NULL_SENTINELS: dict[tuple[str, str], str] = {
    ("paarorende", "telefon"): "INVALID PHONE",
}


@dataclass(slots=True)
class PlannedChange:
    table: str
    pk_column: str
    pk_value: int
    value_column: str
    old_value: str | None
    new_value: str | None
    status: str
    reason: str


async def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize stored phone numbers to E.164 where possible.")
    parser.add_argument("--apply", action="store_true", help="Apply safe updates to the database.")
    parser.add_argument(
        "--report",
        default="tmp/phone-number-normalization-report.csv",
        help="Path to write the manual review report CSV.",
    )
    args = parser.parse_args()

    runtime = build_database_runtime(get_settings())
    try:
        async with runtime.session_factory() as session:
            plans = await collect_changes(session)
        write_report(Path(args.report), plans)
        print_summary(plans, report_path=args.report)
        if args.apply:
            async with runtime.session_factory() as session:
                await apply_changes(session, plans)
            print("Applied safe phone-number updates.")
    finally:
        await runtime.aclose()


async def collect_changes(session) -> list[PlannedChange]:
    plans: list[PlannedChange] = []
    for table, pk_column, value_column in TABLES:
        result = await session.execute(
            text(f"SELECT {pk_column} AS pk_value, {value_column} AS phone_value FROM public.{table}")
        )
        for row in result.mappings():
            analysis = analyze_phone_number(row["phone_value"])
            old_value = row["phone_value"]
            new_value = old_value
            status = "unchanged"
            reason = analysis.reason

            if analysis.status == "empty" and old_value is not None:
                new_value = None
                status = "blank_to_null"
            elif analysis.normalized is not None:
                new_value = analysis.normalized
                status = "normalized" if new_value != old_value else "already_e164"
            elif analysis.status == "invalid":
                if is_obviously_false_phone_number(old_value):
                    sentinel = NON_NULL_SENTINELS.get((table, value_column))
                    new_value = sentinel
                    status = "obvious_false_to_fake" if sentinel is not None else "obvious_false_to_null"
                else:
                    status = "manual_review"

            plans.append(
                PlannedChange(
                    table=table,
                    pk_column=pk_column,
                    pk_value=int(row["pk_value"]),
                    value_column=value_column,
                    old_value=old_value,
                    new_value=new_value,
                    status=status,
                    reason=reason,
                )
            )
    return plans


def write_report(path: Path, plans: list[PlannedChange]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["table", "pk_column", "pk_value", "value_column", "old_value", "new_value", "status", "reason"],
        )
        writer.writeheader()
        for plan in plans:
            if plan.status == "manual_review":
                writer.writerow(
                    {
                        "table": plan.table,
                        "pk_column": plan.pk_column,
                        "pk_value": plan.pk_value,
                        "value_column": plan.value_column,
                        "old_value": plan.old_value,
                        "new_value": plan.new_value,
                        "status": plan.status,
                        "reason": plan.reason,
                    }
                )


def print_summary(plans: list[PlannedChange], *, report_path: str) -> None:
    by_table: dict[str, Counter[str]] = {}
    for plan in plans:
        by_table.setdefault(plan.table, Counter())[plan.status] += 1

    for table, counts in by_table.items():
        total = sum(counts.values())
        print(f"[{table}] total={total}")
        for status, count in sorted(counts.items()):
            print(f"  {status}: {count}")
    print(f"Manual review report: {report_path}")


async def apply_changes(session, plans: list[PlannedChange]) -> None:
    async with session.begin():
        for table, pk_column, value_column in TABLES:
            table_plans = [
                plan
                for plan in plans
                if plan.table == table and plan.status in {"normalized", "blank_to_null", "obvious_false_to_null", "obvious_false_to_fake"}
            ]
            if not table_plans:
                continue
            await session.execute(
                text(
                    f"UPDATE public.{table} "
                    f"SET {value_column} = :new_value "
                    f"WHERE {pk_column} = :pk_value"
                ),
                [
                    {
                        "new_value": plan.new_value,
                        "pk_value": plan.pk_value,
                    }
                    for plan in table_plans
                ],
            )
            print(f"Updated {len(table_plans)} rows in {table}.")


if __name__ == "__main__":
    asyncio.run(main())
