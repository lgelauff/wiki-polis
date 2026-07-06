"""add demo participant marker (#223)

Revision ID: 7e9f01234567
Revises: 6d8e9f012345
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e9f01234567'
down_revision = '6d8e9f012345'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('participants', sa.Column('is_demo', sa.Boolean(),
                                            nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('participants', 'is_demo')
