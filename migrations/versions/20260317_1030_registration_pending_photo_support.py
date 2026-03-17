"""pending registration photo support

Revision ID: 20260317_1030
Revises: 20260316_1500
Create Date: 2026-03-17 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_1030"
down_revision = "20260316_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nytt_personal", sa.Column("photo_sha1", sa.Text(), nullable=True))
    op.add_column("nytt_personal", sa.Column("photo_filetype", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("nytt_personal", "photo_filetype")
    op.drop_column("nytt_personal", "photo_sha1")
