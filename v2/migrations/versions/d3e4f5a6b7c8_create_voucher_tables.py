"""create voucher_batches and voucher_codes tables

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-09-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e4f5a6b7c8'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'voucher_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['conversations.id'],
            ondelete='CASCADE',
        ),
    )
    op.create_index(
        'ix_voucher_batches_conversation_id', 'voucher_batches', ['conversation_id'],
    )
    op.create_table(
        'voucher_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('code_hmac', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='unused'),
        sa.Column('participant_id', sa.Integer(), nullable=True),
        sa.Column('reserved_until', sa.DateTime(), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['batch_id'], ['voucher_batches.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['participant_id'], ['participants.id'],
            ondelete='SET NULL',
        ),
        sa.UniqueConstraint('code_hmac', name='uq_voucher_codes_code_hmac'),
        sa.UniqueConstraint('participant_id', name='uq_voucher_codes_participant_id'),
        sa.CheckConstraint(
            "status IN ('unused', 'reserved', 'redeemed', 'revoked')",
            name='ck_voucher_codes_status',
        ),
    )
    op.create_index('ix_voucher_codes_batch_id', 'voucher_codes', ['batch_id'])
    op.create_index('ix_voucher_codes_status', 'voucher_codes', ['status'])


def downgrade():
    op.drop_index('ix_voucher_codes_status', table_name='voucher_codes')
    op.drop_index('ix_voucher_codes_batch_id', table_name='voucher_codes')
    op.drop_table('voucher_codes')
    op.drop_index('ix_voucher_batches_conversation_id', table_name='voucher_batches')
    op.drop_table('voucher_batches')
