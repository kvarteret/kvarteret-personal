"""add session impersonation metadata

Revision ID: 20260319_1430
Revises: 20260319_1215
Create Date: 2026-03-19 14:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_1430"
down_revision = "20260319_1215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("web_sessions", sa.Column("impersonator_auth_user_id", sa.UUID(), nullable=True))
    op.add_column("web_sessions", sa.Column("impersonator_user_account_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_web_sessions_impersonator_user_account_id",
        "web_sessions",
        "user_accounts",
        ["impersonator_user_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_web_sessions_impersonator_user_account_id", "web_sessions", type_="foreignkey")
    op.drop_column("web_sessions", "impersonator_user_account_id")
    op.drop_column("web_sessions", "impersonator_auth_user_id")
