"""add private admin notes to conversations

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-09-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column('admin_notes', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_column('admin_notes')
