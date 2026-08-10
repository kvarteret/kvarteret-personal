from __future__ import annotations

from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_choice_label_migration_backfills_existing_applications(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE assignment_roles ("
                "id INTEGER PRIMARY KEY, name TEXT, group_id INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE volunteer_application_invites ("
                "id INTEGER PRIMARY KEY, initial_role_id INTEGER, "
                "first_choice_group_id INTEGER, second_choice_group_id INTEGER)"
            )
        )
        connection.execute(
            text("INSERT INTO groups (id, name) VALUES (1, 'Skjenkegruppen')")
        )
        connection.execute(
            text(
                "INSERT INTO assignment_roles (id, name, group_id) "
                "VALUES (7, 'Halvtimen-skjenker', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO volunteer_application_invites "
                "(id, initial_role_id, first_choice_group_id, second_choice_group_id) "
                "VALUES (10, 7, 1, 1)"
            )
        )

        migration = import_module(
            "migrations.versions.20260810_1400_preserve_public_choice_labels"
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )
        migration.upgrade()

        row = connection.execute(
            text(
                "SELECT first_choice_label, second_choice_label "
                "FROM volunteer_application_invites WHERE id = 10"
            )
        ).mappings().one()
        assert row == {
            "first_choice_label": "Halvtimen-skjenker",
            "second_choice_label": "Skjenkegruppen",
        }
        assert {
            column["name"]
            for column in inspect(connection).get_columns(
                "volunteer_application_invites"
            )
        } >= {"first_choice_label", "second_choice_label"}
