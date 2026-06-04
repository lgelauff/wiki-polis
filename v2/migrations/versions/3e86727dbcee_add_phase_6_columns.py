"""add phase 6 columns

Revision ID: 3e86727dbcee
Revises: a3f1c8e2d905
Create Date: 2026-06-04 14:51:48.393965

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3e86727dbcee'
down_revision = 'a3f1c8e2d905'
branch_labels = None
depends_on = None


def upgrade():
    # conversations — phase toggle + Phase 6 Polis conversation mapping.
    # UNIQUE constraint on phase6_polis_conversation_id enforces 1-to-1 mapping
    # and converts a double-init race into a loud IntegrityError.
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phase_informed_voting', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('phase6_polis_conversation_id',
                                      sa.String(length=50), nullable=True))
        batch_op.create_unique_constraint('uq_conversations_phase6_polis_conversation_id',
                                          ['phase6_polis_conversation_id'])

    # featured_statements — Phase 6 Polis statement ID mapping.
    # UNIQUE on (conversation_id, phase6_polis_statement_id) mirrors the existing
    # constraint on (conversation_id, polis_statement_id). NULL values are excluded
    # by SQL semantics so un-seeded rows do not conflict.
    with op.batch_alter_table('featured_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phase6_polis_statement_id',
                                      sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_featured_statements_phase6_polis_statement_id',
                                          ['conversation_id', 'phase6_polis_statement_id'])

    op.create_index('ix_featured_statements_phase6_polis_statement_id',
                    'featured_statements',
                    ['conversation_id', 'phase6_polis_statement_id'],
                    unique=False)


def downgrade():
    op.drop_index('ix_featured_statements_phase6_polis_statement_id',
                  table_name='featured_statements')

    with op.batch_alter_table('featured_statements', schema=None) as batch_op:
        batch_op.drop_constraint('uq_featured_statements_phase6_polis_statement_id',
                                 type_='unique')
        batch_op.drop_column('phase6_polis_statement_id')

    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_constraint('uq_conversations_phase6_polis_conversation_id',
                                 type_='unique')
        batch_op.drop_column('phase6_polis_conversation_id')
        batch_op.drop_column('phase_informed_voting')
