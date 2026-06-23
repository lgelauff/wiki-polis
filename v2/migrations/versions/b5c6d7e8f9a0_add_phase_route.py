"""add consultation phase route (#173)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c6d7e8f9a0'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phase_route', sa.String(length=32),
                                      nullable=False, server_default='default_7'))


def downgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('phase_route')
