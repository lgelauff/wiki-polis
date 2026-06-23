"""add conversation bans (#60)

Revision ID: c4d5e6f7a8b9
Revises: b4c5d6e7f8a9
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'conversation_bans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('banned_by_id', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('lifted_at', sa.DateTime(), nullable=True),
        sa.Column('lifted_by_id', sa.Integer(), nullable=True),
        sa.Column('lift_summary', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['banned_by_id'], ['participants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lifted_by_id'], ['participants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('conversation_bans', schema=None) as batch_op:
        batch_op.create_index(
            'ix_conversation_bans_conversation_participant',
            ['conversation_id', 'participant_id'],
        )


def downgrade():
    with op.batch_alter_table('conversation_bans', schema=None) as batch_op:
        batch_op.drop_index('ix_conversation_bans_conversation_participant')
    op.drop_table('conversation_bans')
