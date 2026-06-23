"""add recommended quantities config (#160)

Revision ID: a4b5c6d7e8f9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e8f9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recommended_quantities', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('recommended_quantities')
