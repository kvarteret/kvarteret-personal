"""Add bounded event enthusiasm responses, without event content.

Revision ID: 20261001_1400
Revises: 20261001_1300
"""

from alembic import op
import sqlalchemy as sa

revision = "20261001_1400"
down_revision = "20261001_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_interest",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("source_hash", sa.String(64), primary_key=True),
        sa.Column("taps", sa.SmallInteger(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '90 days'"),
        ),
        sa.CheckConstraint("taps BETWEEN 1 AND 12", name="event_interest_taps_bounds"),
        sa.CheckConstraint(
            "source_hash ~ '^[a-f0-9]{64}$'", name="event_interest_source_hash_format"
        ),
        schema="public",
    )
    op.create_index(
        "event_interest_expiry_idx", "event_interest", ["expires_at"], schema="public"
    )
    # Only the backend connection owns access; never expose via Supabase's public API.
    op.execute("ALTER TABLE public.event_interest ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.event_interest FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("event_interest", schema="public")
