"""Link individual admin accounts to volunteers and mark legacy logins."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_1300'
down_revision = '20261006_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_accounts', sa.Column('volunteer_id', sa.BigInteger()), schema='public')
    op.add_column('user_accounts', sa.Column('is_legacy_account', sa.Boolean(), nullable=False, server_default=sa.false()), schema='public')
    op.create_foreign_key('user_accounts_volunteer_id_fkey', 'user_accounts', 'volunteer_records', ['volunteer_id'], ['id'], source_schema='public', referent_schema='public')
    op.create_unique_constraint('uq_user_accounts_volunteer', 'user_accounts', ['volunteer_id'], schema='public')


def downgrade():
    op.drop_constraint('uq_user_accounts_volunteer', 'user_accounts', schema='public')
    op.drop_constraint('user_accounts_volunteer_id_fkey', 'user_accounts', schema='public')
    op.drop_column('user_accounts', 'is_legacy_account', schema='public')
    op.drop_column('user_accounts', 'volunteer_id', schema='public')
