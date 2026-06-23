"""add xid key version marker (#96)

Revision ID: 4b6c7d8e9f01
Revises: e3f4a5b6c7d8
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b6c7d8e9f01'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('participants', sa.Column('xid_key_version', sa.Integer(),
                                            nullable=False, server_default='1'))
    op.alter_column('participants', 'xid_key_version', server_default='2')


def downgrade():
    op.drop_column('participants', 'xid_key_version')
