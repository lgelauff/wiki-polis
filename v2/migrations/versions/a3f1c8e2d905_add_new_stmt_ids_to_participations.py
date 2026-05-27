"""add new_stmt_ids to participations

Revision ID: a3f1c8e2d905
Revises: 99f8b42af697
Create Date: 2026-05-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f1c8e2d905'
down_revision = '99f8b42af697'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'new_stmt_ids',
            sa.JSON(),
            nullable=False,
            server_default='[]',
        ))


def downgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.drop_column('new_stmt_ids')
