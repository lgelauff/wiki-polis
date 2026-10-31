"""add reminders and their deliveries

Revision ID: a7b8c9d0e1f2
Revises: e1f2a3b4c5d6
Create Date: 2026-10-31 12:00:00.000000

The sender core for reminders (#577). Two new tables and two consultation
settings: the wiki reminders go out from (Meta unless a super admin picks another)
and whether a talk-page note names the consultation (off). Nothing is sent yet.
Totals are counts over the deliveries; a delivery unlinked from its person keeps
counting.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None

_STATUSES = ('pending', 'sent', 'dry_run', 'combined', 'skipped_expired',
             'skipped_optout', 'not_sent_limit', 'failed')
_REASONS = ('not_emailable', 'refused', 'nobots', 'throttled', 'blocked', 'api_error')


def _in_list(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade():
    with op.batch_alter_table('conversations') as batch:
        batch.add_column(sa.Column('reminder_wiki', sa.String(length=32), nullable=False,
                                   server_default='metawiki'))
        batch.add_column(sa.Column('reminder_talk_names_consultation', sa.Boolean(),
                                   nullable=False, server_default=sa.false()))

    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('reminder_type', sa.String(length=32), nullable=False),
        sa.Column('phase_key', sa.String(length=32), nullable=True),
        sa.Column('send_day', sa.Date(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['participants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reminders_conversation_id', 'reminders', ['conversation_id'])
    op.create_index('ix_reminders_send_day', 'reminders', ['send_day'])

    op.create_table(
        'reminder_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reminder_id', sa.Integer(), nullable=False),
        sa.Column('participation_id', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('reason', sa.String(length=16), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('sent_via', sa.String(length=32), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('attempted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['reminder_id'], ['reminders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participation_id'], ['participations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reminder_id', 'participation_id', 'channel',
                            name='uq_reminder_delivery_target'),
        sa.CheckConstraint("channel IN ('email', 'talk')", name='ck_reminder_delivery_channel'),
        sa.CheckConstraint(_in_list('status', _STATUSES), name='ck_reminder_delivery_status'),
        sa.CheckConstraint(
            f"(status = 'failed' AND reason IS NOT NULL AND {_in_list('reason', _REASONS)}) "
            "OR (status <> 'failed' AND reason IS NULL)",
            name='ck_reminder_delivery_reason',
        ),
    )
    op.create_index('ix_reminder_deliveries_status', 'reminder_deliveries', ['status'])
    op.create_index('ix_reminder_deliveries_participation_id', 'reminder_deliveries',
                    ['participation_id'])


def downgrade():
    op.drop_index('ix_reminder_deliveries_participation_id', table_name='reminder_deliveries')
    op.drop_index('ix_reminder_deliveries_status', table_name='reminder_deliveries')
    op.drop_table('reminder_deliveries')
    op.drop_index('ix_reminders_send_day', table_name='reminders')
    op.drop_index('ix_reminders_conversation_id', table_name='reminders')
    op.drop_table('reminders')
    with op.batch_alter_table('conversations') as batch:
        batch.drop_column('reminder_talk_names_consultation')
        batch.drop_column('reminder_wiki')
