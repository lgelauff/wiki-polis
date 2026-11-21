"""add voucher_batches.link_resume_until (#412)

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
Create Date: 2026-11-21 15:00:00.000000

An optional moment per batch after which a link carrying a code no longer signs a
returning holder back in: the code page opens and the code has to be typed. NULL
keeps today's behaviour (links resume for as long as the code lives), so existing
batches are unchanged.

Rollback: additive. A downgrade drops the column and with it every date set.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('voucher_batches') as batch:
        batch.add_column(sa.Column('link_resume_until', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('voucher_batches') as batch:
        batch.drop_column('link_resume_until')
