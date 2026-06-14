"""add last_engagement to participations (#42)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    # Recency of a participant's most recent meaningful action (#42) — action-based, not
    # a passive last-seen. Nullable: existing rows have no recorded action yet.
    op.add_column('participations',
                  sa.Column('last_engagement', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('participations', 'last_engagement')
