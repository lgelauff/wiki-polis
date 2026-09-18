"""add gated-process access settings and migrate legacy admission

Revision ID: b0c1d2e3f4a5
Revises: a8b9c0d1e2f3
Create Date: 2026-09-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def _backfill_participation_invites(connection):
    """Materialise the historical admission relation without duplicates."""
    connection.execute(sa.text(
        """
        INSERT INTO conversation_invites
            (conversation_id, mw_username, mw_user_id, invited_by, created_at)
        SELECT
            participations.conversation_id,
            participants.mw_username,
            participants.mw_user_id,
            'migration',
            participations.accepted_at
        FROM participations
        JOIN participants ON participants.id = participations.participant_id
        JOIN conversations ON conversations.id = participations.conversation_id
        WHERE conversations.gated = 1
          AND conversations.access_policy <> 'demo'
          AND NOT EXISTS (
              SELECT 1
              FROM conversation_invites
              WHERE conversation_invites.conversation_id = participations.conversation_id
                AND conversation_invites.mw_username = participants.mw_username
          )
        """
    ))


def upgrade():
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column(
            'gated', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'gating_type', sa.String(length=32), nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'announce', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'information', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'results_shared', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'show_usernames', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'access_request_text', sa.Text(), nullable=True,
        ))
        batch_op.create_check_constraint(
            'ck_conversation_gating_type',
            "gating_type IS NULL OR gating_type IN "
            "('invite_only', 'voucher', 'wiki_based')",
        )

    with op.batch_alter_table('conversation_invites') as batch_op:
        batch_op.add_column(sa.Column('mw_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column(
            'invited_by', sa.String(length=255), nullable=True,
        ))

    connection = op.get_bind()
    connection.execute(sa.text(
        """
        UPDATE conversations
        SET
            gated = CASE
                WHEN access_policy = 'invite_only' THEN 1
                WHEN access_policy = 'public'
                     AND NULLIF(TRIM(eligibility_event_id), '') IS NOT NULL
                    THEN 1
                ELSE 0
            END,
            gating_type = CASE
                WHEN access_policy = 'invite_only' THEN 'invite_only'
                ELSE NULL
            END,
            announce = CASE
                WHEN access_policy = 'public'
                     AND NULLIF(TRIM(eligibility_event_id), '') IS NOT NULL
                    THEN 1
                ELSE 0
            END,
            information = CASE
                WHEN access_policy = 'public'
                     AND NULLIF(TRIM(eligibility_event_id), '') IS NOT NULL
                    THEN 1
                ELSE 0
            END,
            results_shared = CASE
                WHEN access_policy = 'public'
                     AND NULLIF(TRIM(eligibility_event_id), '') IS NOT NULL
                    THEN phase_public_results
                ELSE 0
            END,
            show_usernames = CASE
                WHEN access_policy = 'public'
                     AND NULLIF(TRIM(eligibility_event_id), '') IS NOT NULL
                    THEN phase_public_results
                ELSE 0
            END,
            eligibility_event_id = CASE
                WHEN access_policy = 'invite_only' THEN NULL
                ELSE eligibility_event_id
            END,
            eligibility_label = CASE
                WHEN access_policy = 'invite_only' THEN NULL
                ELSE eligibility_label
            END
        """
    ))
    connection.execute(sa.text(
        """
        UPDATE conversation_invites
        SET mw_user_id = (
            SELECT participants.mw_user_id
            FROM participants
            WHERE participants.mw_username = conversation_invites.mw_username
        )
        WHERE mw_user_id IS NULL
        """
    ))
    _backfill_participation_invites(connection)


def downgrade():
    with op.batch_alter_table('conversation_invites') as batch_op:
        batch_op.drop_column('invited_by')
        batch_op.drop_column('mw_user_id')

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_constraint(
            'ck_conversation_gating_type', type_='check',
        )
        batch_op.drop_column('access_request_text')
        batch_op.drop_column('show_usernames')
        batch_op.drop_column('results_shared')
        batch_op.drop_column('information')
        batch_op.drop_column('announce')
        batch_op.drop_column('gating_type')
        batch_op.drop_column('gated')
