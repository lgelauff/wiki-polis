"""add content flags (#138)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


flag_content_type = sa.Enum('statement', 'argument', name='flag_content_type')
flag_category = sa.Enum('personal_attack', 'privacy', 'off_topic', 'other', name='flag_category')
flag_status = sa.Enum('open', 'resolved', name='flag_status')


def upgrade():
    op.create_table(
        'content_flags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=True),
        sa.Column('content_type', flag_content_type, nullable=False),
        sa.Column('statement_tid', sa.Integer(), nullable=True),
        sa.Column('argument_id', sa.Integer(), nullable=True),
        sa.Column('category', flag_category, nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('status', flag_status, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_id', sa.Integer(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.CheckConstraint(
            "((content_type = 'statement' AND statement_tid IS NOT NULL AND argument_id IS NULL) "
            "OR (content_type = 'argument' AND argument_id IS NOT NULL AND statement_tid IS NULL))",
            name='content_flag_target_check',
        ),
        sa.ForeignKeyConstraint(['argument_id'], ['arguments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['participants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.create_index(
            'ix_content_flags_conversation_status',
            ['conversation_id', 'status', 'created_at'],
        )
        batch_op.create_index('ix_content_flags_argument_id', ['argument_id'])
        batch_op.create_index(
            'ix_content_flags_statement_tid',
            ['conversation_id', 'statement_tid'],
        )


def downgrade():
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.drop_index('ix_content_flags_statement_tid')
        batch_op.drop_index('ix_content_flags_argument_id')
        batch_op.drop_index('ix_content_flags_conversation_status')
    op.drop_table('content_flags')
    flag_status.drop(op.get_bind(), checkfirst=True)
    flag_category.drop(op.get_bind(), checkfirst=True)
    flag_content_type.drop(op.get_bind(), checkfirst=True)
