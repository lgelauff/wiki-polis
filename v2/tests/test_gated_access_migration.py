"""Legacy gated-access migration coverage."""

from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from flask import g
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from db import Conversation, ConversationInvite, Participation, Participant, db
from services.access import check_access
from tests.conftest import login


MIGRATION_PATH = (
    Path(__file__).parents[1] / 'migrations' / 'versions'
    / 'b0c1d2e3f4a5_add_gated_access_settings.py'
)


def _migration_module():
    spec = spec_from_file_location('gated_access_migration', MIGRATION_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old_schema(metadata):
    sa.Table(
        'conversations',
        metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('access_policy', sa.String(20), nullable=False),
        sa.Column('eligibility_event_id', sa.String(80), nullable=True),
        sa.Column('eligibility_label', sa.String(255), nullable=True),
        sa.Column('phase_public_results', sa.Boolean, nullable=False),
    )
    sa.Table(
        'participants',
        metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('mw_user_id', sa.Integer, nullable=False),
        sa.Column('mw_username', sa.String(255), nullable=False),
    )
    sa.Table(
        'participations',
        metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('participant_id', sa.Integer, nullable=False),
        sa.Column('conversation_id', sa.Integer, nullable=False),
        sa.Column('accepted_at', sa.DateTime, nullable=False),
    )
    sa.Table(
        'conversation_invites',
        metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('conversation_id', sa.Integer, nullable=False),
        sa.Column('mw_username', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.UniqueConstraint('conversation_id', 'mw_username'),
    )


def test_migration_maps_legacy_access_is_idempotent_and_downgrades():
    migration = _migration_module()
    metadata = sa.MetaData()
    _old_schema(metadata)
    engine = sa.create_engine('sqlite://')
    metadata.create_all(engine)
    accepted = datetime(2026, 1, 2, 3, 4, 5)

    with engine.begin() as connection:
        connection.execute(sa.text(
            """
            INSERT INTO conversations
                (id, access_policy, eligibility_event_id, eligibility_label,
                 phase_public_results)
            VALUES
                (1, 'public', 'public-event', 'Legacy check', 1),
                (2, 'invite_only', 'invite-event', 'Old invite check', 0),
                (3, 'demo', NULL, NULL, 1),
                (4, 'public', NULL, NULL, 0)
            """
        ))
        connection.execute(sa.text(
            """
            INSERT INTO participants (id, mw_user_id, mw_username)
            VALUES
                (1, 1001, 'joined-public'),
                (2, 1002, 'joined-invite'),
                (3, 1003, 'joined-demo'),
                (4, 1004, 'old-invite')
            """
        ))
        connection.execute(sa.text(
            """
            INSERT INTO participations
                (id, participant_id, conversation_id, accepted_at)
            VALUES
                (1, 1, 1, :accepted),
                (2, 2, 2, :accepted),
                (3, 3, 3, :accepted)
            """
        ), {'accepted': accepted})
        connection.execute(sa.text(
            """
            INSERT INTO conversation_invites
                (conversation_id, mw_username, created_at)
            VALUES (2, 'old-invite', :accepted)
            """
        ), {'accepted': accepted})

        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        conversations = {
            row['id']: row for row in connection.execute(sa.text(
                """
                SELECT id, access_policy, gated, gating_type, announce,
                       information, results_shared, show_usernames,
                       eligibility_event_id, eligibility_label
                FROM conversations
                ORDER BY id
                """
            )).mappings()
        }
        assert dict(conversations[1]) == {
            'id': 1, 'access_policy': 'public', 'gated': 1,
            'gating_type': None, 'announce': 1, 'information': 1,
            'results_shared': 1, 'show_usernames': 1,
            'eligibility_event_id': 'public-event',
            'eligibility_label': 'Legacy check',
        }
        assert conversations[2]['gated'] == 1
        assert conversations[2]['gating_type'] == 'invite_only'
        assert conversations[2]['eligibility_event_id'] is None
        assert conversations[2]['eligibility_label'] is None
        assert conversations[3]['gated'] == 0
        assert conversations[4]['gated'] == 0

        invite_rows = connection.execute(sa.text(
            """
            SELECT conversation_id, mw_username, mw_user_id, invited_by,
                   created_at
            FROM conversation_invites
            ORDER BY conversation_id, mw_username
            """
        )).mappings().all()
        assert {
            (row['conversation_id'], row['mw_username'], row['mw_user_id'],
             row['invited_by'])
            for row in invite_rows
        } == {
            (1, 'joined-public', 1001, 'migration'),
            (2, 'joined-invite', 1002, 'migration'),
            (2, 'old-invite', 1004, None),
        }
        assert all(row['conversation_id'] != 3 for row in invite_rows)

        before = connection.execute(sa.text(
            'SELECT COUNT(*) FROM conversation_invites'
        )).scalar_one()
        migration._backfill_participation_invites(connection)
        after = connection.execute(sa.text(
            'SELECT COUNT(*) FROM conversation_invites'
        )).scalar_one()
        assert after == before

        migration.downgrade()
        assert 'gated' not in {
            column['name']
            for column in sa.inspect(connection).get_columns('conversations')
        }
        assert 'mw_user_id' not in {
            column['name']
            for column in sa.inspect(connection).get_columns('conversation_invites')
        }


def test_migrated_public_event_rejects_fresh_join_and_imported_invite_allows(
    client, participant, app,
):
    public_event = Conversation(
        slug='migrated-public-event',
        polis_id='migrated-public',
        title='Migrated public event',
        active=True,
        access_policy='public',
        gated=True,
        gating_type=None,
        eligibility_event_id='legacy-event',
        eligibility_label='Legacy eligibility',
    )
    invite_only = Conversation(
        slug='migrated-invite',
        polis_id='migrated-invite',
        title='Migrated invite-only',
        active=True,
        access_policy='invite_only',
        gated=True,
        gating_type='invite_only',
    )
    db.session.add_all([public_event, invite_only])
    db.session.flush()
    db.session.add_all([
        Participation(
            participant_id=participant.id,
            conversation_id=invite_only.id,
            pseudonym='imported-otter',
        ),
        ConversationInvite(
            conversation_id=invite_only.id,
            mw_username=participant.mw_username,
            mw_user_id=participant.mw_user_id,
            invited_by='migration',
        ),
    ])
    fresh = Participant(
        mw_user_id=70001,
        mw_username='fresh-account',
        xid='f' * 64,
    )
    db.session.add(fresh)
    db.session.commit()

    login(client, fresh.mw_username)
    g.pop('participant', None)
    refused = client.post(
        '/api/v1/conversations/migrated-public-event/participation',
        json={'pseudonym': 'fresh-fox'},
    )
    assert refused.status_code == 403
    assert refused.get_json()['error']['details'] == {
        'slug': 'migrated-public-event',
        'title': 'Migrated public event',
        'gatingType': None,
        'viewer': 'refused',
        'certainty': 'inconclusive',
        'reason': 'access-policy-not-configured',
        'loginOptions': [],
        'sharedResults': [],
    }

    login(client, participant.mw_username)
    g.pop('participant', None)
    assert ConversationInvite.query.filter_by(
        conversation_id=invite_only.id,
        mw_user_id=participant.mw_user_id,
    ).count() == 1
    assert check_access(invite_only, participant).allowed is True
    workspace = client.get('/api/v1/conversations/migrated-invite/workspace')
    assert workspace.status_code == 200, workspace.get_json()
