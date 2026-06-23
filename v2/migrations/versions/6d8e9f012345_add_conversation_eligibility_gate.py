"""add conversation eligibility gate (#146)

Revision ID: 6d8e9f012345
Revises: 5c7d8e9f0123
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d8e9f012345'
down_revision = '5c7d8e9f0123'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('eligibility_event_id',
                                             sa.String(length=80), nullable=True))
    op.add_column('conversations', sa.Column('eligibility_label',
                                             sa.String(length=255), nullable=True))
    op.add_column('participations', sa.Column('eligibility_status',
                                              sa.String(length=16), nullable=True))
    op.add_column('participations', sa.Column('eligibility_checked_at',
                                              sa.DateTime(), nullable=True))
    op.add_column('participations', sa.Column('eligibility_detail',
                                              sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('participations', 'eligibility_detail')
    op.drop_column('participations', 'eligibility_checked_at')
    op.drop_column('participations', 'eligibility_status')
    op.drop_column('conversations', 'eligibility_label')
    op.drop_column('conversations', 'eligibility_event_id')
