"""persist the default moderation policy for future statements

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows remain NULL until their live Polis setting is reconciled. This
    # preserves an intentional non-strict policy instead of blindly changing it.
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column(
            'statement_moderation_policy', sa.String(length=20), nullable=True,
        ))
        batch_op.create_check_constraint(
            'ck_conversation_statement_moderation_policy',
            "statement_moderation_policy IN ('moderate', 'auto_approve')",
        )


def downgrade():
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_constraint(
            'ck_conversation_statement_moderation_policy', type_='check',
        )
        batch_op.drop_column('statement_moderation_policy')
