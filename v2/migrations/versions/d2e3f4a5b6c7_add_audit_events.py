"""add audit_events table (#135)

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Append-only accountability trail (#135). ON DELETE SET NULL so the record
    # outlives a deleted participant/conversation.
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('actor_participant_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('operation', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=True),
        sa.Column('target_id', sa.String(length=64), nullable=True),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['actor_participant_id'], ['participants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index('ix_audit_events_conv_ts', ['conversation_id', 'ts'])
        batch_op.create_index('ix_audit_events_actor_ts', ['actor_participant_id', 'ts'])


def downgrade():
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_events_actor_ts')
        batch_op.drop_index('ix_audit_events_conv_ts')
    op.drop_table('audit_events')
