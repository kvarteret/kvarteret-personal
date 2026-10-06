"""Durably capture booking requests before Crescat forwarding."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261006_1500"
down_revision = "20261001_1400"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "booking_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "submission_id",
            "content_hash",
            name="booking_requests_submission_content_key",
        ),
        schema="public",
    )
    op.execute("ALTER TABLE public.booking_requests ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.booking_requests FROM PUBLIC, anon, authenticated")


def downgrade():
    op.drop_table("booking_requests", schema="public")
