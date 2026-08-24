"""enforce case-insensitive admin identity uniqueness

Revision ID: 20260824_0900
Revises: 20260814_1200
Create Date: 2026-08-24 09:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260824_0900"
down_revision = "20260814_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expression indexes match the case-insensitive lookups used by login and
    # admin-account reconciliation. PostgreSQL will reject this migration with
    # a clear duplicate-key error if pre-existing conflicting rows need review.
    op.execute(
        "CREATE UNIQUE INDEX uq_user_accounts_email_ci "
        "ON public.user_accounts (lower(email))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_user_accounts_username_ci "
        "ON public.user_accounts (lower(username))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.uq_user_accounts_username_ci")
    op.execute("DROP INDEX IF EXISTS public.uq_user_accounts_email_ci")
