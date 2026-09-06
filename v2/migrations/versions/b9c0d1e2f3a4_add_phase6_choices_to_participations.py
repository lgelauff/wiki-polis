"""add phase6_choices to participations

The informed-vote write path already held the participant's choice and discarded
it, storing only when they voted (last_engagement) and not what. Every later read
then had to reconstruct it from Particiapi's /participant, which returns statement
ids without their values -- so the interface could say "answered" but never "you
chose disagree", and a participant could silently overwrite a considered vote.

Mirrors phase6_card_order: same table, same phase, same JSON shape, written on the
same request. Safe as a store rather than a cache because the API is the only
informed-vote write path since the Jinja route was deleted.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9c0d1e2f3a4'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phase6_choices', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('participations', schema=None) as batch_op:
        batch_op.drop_column('phase6_choices')
