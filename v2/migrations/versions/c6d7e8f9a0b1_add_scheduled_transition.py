"""add scheduled phase transition fields (#164)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scheduled_transition_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('scheduled_transition_target', sa.String(length=32),
                                      nullable=True))
        batch_op.add_column(sa.Column('scheduled_transition_frozen', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('scheduled_transition_frozen')
        batch_op.drop_column('scheduled_transition_target')
        batch_op.drop_column('scheduled_transition_at')
