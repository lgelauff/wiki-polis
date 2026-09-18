"""add participant account kind and conversation scope

Revision ID: 6a7090c4c5d7
Revises: a8b9c0d1e2f3
Create Date: 2026-09-18 09:59:02.978217

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a7090c4c5d7'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('participants', schema=None) as batch_op:
        # Existing rows are Wikimedia identities. Nullable Wikimedia fields let
        # voucher identities carry only their account kind and scope.
        batch_op.alter_column(
            'mw_user_id',
            existing_type=sa.Integer(),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            'mw_username',
            existing_type=sa.String(length=255),
            existing_nullable=False,
            nullable=True,
        )
        # Deliberately String, with no check constraint: a future auth method can
        # add a discriminator without migrating all live participant rows.
        batch_op.add_column(sa.Column(
            'account_kind', sa.String(length=32),
            nullable=False,
            server_default='wikimedia',
        ))
        batch_op.add_column(sa.Column(
            'conversation_id', sa.Integer(), nullable=True,
        ))
        batch_op.create_foreign_key(
            'fk_participants_conversation_id',
            'conversations',
            ['conversation_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade():
    with op.batch_alter_table('participants', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_participants_conversation_id', type_='foreignkey',
        )
        batch_op.drop_column('conversation_id')
        batch_op.drop_column('account_kind')
        batch_op.alter_column(
            'mw_user_id',
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            'mw_username',
            existing_type=sa.String(length=255),
            existing_nullable=True,
            nullable=False,
        )
