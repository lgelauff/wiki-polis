"""add phase_cleanup column (#163)

Revision ID: c1a2b3d4e5f6
Revises: f667548e9519
Create Date: 2026-06-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a2b3d4e5f6'
down_revision = 'f667548e9519'
branch_labels = None
depends_on = None


def upgrade():
    # Cleanup — a passive phase between argument mapping and informed voting (#163).
    # Default off so every existing conversation is unaffected.
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phase_cleanup', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('phase_cleanup')
