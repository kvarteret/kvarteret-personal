"""Count every event click in retry-safe batches.

Revision ID: 20261001_1500
Revises: 20261001_1400
"""

from alembic import op
import sqlalchemy as sa

revision = "20261001_1500"
down_revision = "20261001_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_interest_clicks",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("batch_id", sa.Uuid(), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("clicks", sa.SmallInteger(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '90 days'"),
        ),
        sa.CheckConstraint(
            "clicks BETWEEN 1 AND 1000", name="event_interest_clicks_bounds"
        ),
        sa.CheckConstraint(
            "source_hash ~ '^[a-f0-9]{64}$'", name="event_interest_clicks_source_format"
        ),
        schema="public",
    )
    op.create_index(
        "event_interest_clicks_expiry_idx",
        "event_interest_clicks",
        ["expires_at"],
        schema="public",
    )
    op.execute("ALTER TABLE public.event_interest_clicks ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.event_interest_clicks FROM PUBLIC")
    # Preserve previously recorded taps and expiry; no extension is required.
    op.execute("""
        INSERT INTO public.event_interest_clicks (event_id, batch_id, source_hash, clicks, expires_at)
        SELECT event_id, md5(event_id || ':' || source_hash)::uuid, source_hash, taps, expires_at
        FROM public.event_interest
    """)


def downgrade() -> None:
    op.drop_table("event_interest_clicks", schema="public")
