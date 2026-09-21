"""merge gated-access-settings and voucher-identity branches

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5, 6a7090c4c5d7
Create Date: 2026-09-21 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = ('b0c1d2e3f4a5', '6a7090c4c5d7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass