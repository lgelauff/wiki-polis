"""add participation last_engagement (#42)

Revision ID: b4c5d6e7f8a9
Revises: a4b5c6d7e8f9
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8a9'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_engagement', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.drop_column('last_engagement')
