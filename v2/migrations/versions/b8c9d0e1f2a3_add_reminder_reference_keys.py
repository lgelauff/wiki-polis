"""add the keys for wiki-mail references, and the combined-mail pointer

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-21 12:00:00.000000

Every bot wiki-mail carries a reference: its delivery's id, encrypted with a
monthly key (#622). The keys get a table of their own, and each key is deleted
90 days after its last use. A delivery handed out in a combined mail points to
the delivery whose reference that mail carried (``combined_into_id``), so a
reply traces to every consultation in it.

Rollback: the change is additive, so rolling back the code needs no downgrade. A
downgrade drops the keys, after which no reference sent so far can be traced,
and the combined-mail pointers.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reminder_reference_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('key', sa.LargeBinary(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('month', name='uq_reminder_reference_keys_month'),
    )
    with op.batch_alter_table('reminder_deliveries') as batch:
        batch.add_column(sa.Column('combined_into_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_reminder_deliveries_combined_into_id',
                                 'reminder_deliveries', ['combined_into_id'], ['id'],
                                 ondelete='SET NULL')
    op.create_index('ix_reminder_deliveries_combined_into_id', 'reminder_deliveries',
                    ['combined_into_id'])


def downgrade():
    # Drop the foreign key before the index that backs it (MariaDB error 1553).
    with op.batch_alter_table('reminder_deliveries') as batch:
        batch.drop_constraint('fk_reminder_deliveries_combined_into_id', type_='foreignkey')
    op.drop_index('ix_reminder_deliveries_combined_into_id', table_name='reminder_deliveries')
    with op.batch_alter_table('reminder_deliveries') as batch:
        batch.drop_column('combined_into_id')
    op.drop_table('reminder_reference_keys')
