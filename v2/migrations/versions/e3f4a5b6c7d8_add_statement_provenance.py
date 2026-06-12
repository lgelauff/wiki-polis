"""add statement_provenance table (#143)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    # Provenance for derivative statements (#143). One row per derivative; absence = 'new'.
    op.create_table(
        'statement_provenance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('polis_statement_id', sa.Integer(), nullable=False),
        sa.Column('derived_from_tid', sa.Integer(), nullable=False),
        sa.Column('provenance_type', sa.String(length=16), nullable=False),
        sa.Column('link_method', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'polis_statement_id',
                            name='uq_statement_provenance_conv_tid'),
    )

    # Similarity-at-creation scores — many kinds per link (char fallback now, semantic #207 later).
    op.create_table(
        'statement_similarity_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provenance_id', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('scored_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['provenance_id'], ['statement_provenance.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provenance_id', 'model', name='uq_similarity_score_prov_model'),
    )


def downgrade():
    op.drop_table('statement_similarity_scores')
    op.drop_table('statement_provenance')
