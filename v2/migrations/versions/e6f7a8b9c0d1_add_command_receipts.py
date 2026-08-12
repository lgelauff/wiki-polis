"""add durable browser command receipts

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'command_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('command', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('response', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['conversations.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['participant_id'], ['participants.id'], ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "(state = 'pending' AND response IS NULL AND completed_at IS NULL) "
            "OR (state = 'completed' AND response IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name='ck_command_receipt_lifecycle',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'participant_id', 'conversation_id', 'command', 'idempotency_key',
            name='uq_command_receipt_scope_key',
        ),
    )
    op.create_index(
        'ix_command_receipts_created_at',
        'command_receipts', ['created_at'], unique=False,
    )


def downgrade():
    op.drop_index('ix_command_receipts_created_at', table_name='command_receipts')
    op.drop_table('command_receipts')
