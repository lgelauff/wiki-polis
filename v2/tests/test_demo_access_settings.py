"""Demo's fixed access answers: the backfill, the settings guard, creation.

A demo consultation has no access settings of its own. It is never gated, everyone can
see it, and usernames are never shown; these values are stored, not implied. Only a
site admin may move a consultation into or out of demo.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from db import AdminRole, Conversation, db
from tests.conftest import login


MIGRATION_PATH = (
    Path(__file__).parents[1] / 'migrations' / 'versions'
    / 'e1f2a3b4c5d6_store_demo_access_settings.py'
)
FIXED = {
    'gated': False, 'gating_type': None, 'announce': True, 'information': True,
    'results_shared': True, 'show_usernames': False,
}


def _stored(conversation):
    db.session.refresh(conversation)
    return {field: getattr(conversation, field) for field in FIXED}


def _body(conversation, **overrides):
    body = {
        'title': conversation.title, 'introHtml': '', 'outroHtml': '',
        'accessPolicy': conversation.access_policy,
        'gated': False, 'gatingType': None,
        'announce': False, 'information': False, 'resultsShared': False,
        'showUsernames': False, 'accessRequestText': None,
        'eligibilityEventId': '', 'eligibilityLabel': '',
        'recommendationTier': 'medium',
    }
    body.update(overrides)
    return body


def _organizer(client, conversation, participant):
    db.session.add(AdminRole(
        participant_id=participant.id, conversation_id=conversation.id,
        role='organizer',
    ))
    db.session.commit()
    login(client, 'testuser')


def _endpoint(conversation):
    return f'/api/v1/admin/conversations/{conversation.id}/settings'


# ── backfill ────────────────────────────────────────────────────────────────


def _migration_module():
    spec = spec_from_file_location('demo_access_migration', MIGRATION_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_stores_the_fixed_answers_on_demo_rows_only():
    migration = _migration_module()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table(
        'conversations', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('access_policy', sa.String(20), nullable=False),
        sa.Column('gated', sa.Boolean, nullable=False),
        sa.Column('gating_type', sa.String(32), nullable=True),
        sa.Column('announce', sa.Boolean, nullable=False),
        sa.Column('information', sa.Boolean, nullable=False),
        sa.Column('results_shared', sa.Boolean, nullable=False),
        sa.Column('show_usernames', sa.Boolean, nullable=False),
    )
    metadata.create_all(engine)
    columns = ('id, access_policy, gated, gating_type, announce, information,'
               ' results_shared, show_usernames')
    with engine.begin() as connection:
        connection.execute(sa.text(
            f"""
            INSERT INTO conversations ({columns}) VALUES
                (1, 'demo', 1, 'invite_only', 0, 0, 0, 1),
                (2, 'demo', 0, NULL, 0, 1, 0, 0),
                (3, 'invite_only', 1, 'voucher', 0, 0, 0, 1),
                (4, 'public', 0, NULL, 0, 0, 0, 0)
            """
        ))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()  # idempotent

        rows = {row['id']: dict(row) for row in connection.execute(sa.text(
            f'SELECT {columns} FROM conversations ORDER BY id'
        )).mappings()}

    fixed = {'gated': 0, 'gating_type': None, 'announce': 1, 'information': 1,
             'results_shared': 1, 'show_usernames': 0}
    for demo_id in (1, 2):
        assert {k: rows[demo_id][k] for k in fixed} == fixed
    assert rows[3] == {
        'id': 3, 'access_policy': 'invite_only', 'gated': 1, 'gating_type': 'voucher',
        'announce': 0, 'information': 0, 'results_shared': 0, 'show_usernames': 1,
    }
    assert rows[4]['announce'] == 0 and rows[4]['gated'] == 0


# ── the settings guard ──────────────────────────────────────────────────────


def test_site_admin_switch_to_demo_stores_the_fixed_answers(
    admin_client, conversation,
):
    conversation.show_usernames = True
    db.session.commit()

    response = admin_client.put(_endpoint(conversation), json=_body(
        conversation, accessPolicy='demo', showUsernames=True,
    ))

    assert response.status_code == 200
    assert conversation.access_policy == 'demo'
    assert _stored(conversation) == FIXED
    settings = response.get_json()['data']['settings']['conversation']
    assert settings['gated'] is False
    assert settings['resultsShared'] is True
    assert settings['showUsernames'] is False


def test_demo_with_a_gate_is_refused_and_nothing_is_stored(
    admin_client, conversation,
):
    conversation.access_policy = 'demo'
    for field, value in FIXED.items():
        setattr(conversation, field, value)
    db.session.commit()

    response = admin_client.put(_endpoint(conversation), json=_body(
        conversation, title='Changed', gated=True, gatingType='invite_only',
    ))

    assert response.status_code == 400
    assert response.get_json()['error'] == {
        'code': 'validation_failed',
        'message': 'A demo consultation cannot be gated.',
    }
    db.session.refresh(conversation)
    assert conversation.title != 'Changed'
    assert _stored(conversation) == FIXED


def test_organizer_cannot_switch_into_demo(client, conversation, participant):
    _organizer(client, conversation, participant)

    response = client.put(_endpoint(conversation), json=_body(
        conversation, accessPolicy='demo',
    ))

    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'
    db.session.refresh(conversation)
    assert conversation.access_policy == 'public'


def test_organizer_cannot_switch_out_of_demo(client, conversation, participant):
    conversation.access_policy = 'demo'
    db.session.commit()
    _organizer(client, conversation, participant)

    response = client.put(_endpoint(conversation), json=_body(
        conversation, accessPolicy='public',
    ))

    assert response.status_code == 403
    db.session.refresh(conversation)
    assert conversation.access_policy == 'demo'


def test_organizer_saves_a_demo_consultation_and_its_answers_stay_fixed(
    client, conversation, participant,
):
    conversation.access_policy = 'demo'
    db.session.commit()
    _organizer(client, conversation, participant)

    response = client.put(_endpoint(conversation), json=_body(
        conversation, title='Renamed demo', announce=False, showUsernames=True,
    ))

    assert response.status_code == 200
    assert conversation.title == 'Renamed demo'
    assert conversation.access_policy == 'demo'
    assert _stored(conversation) == FIXED


def test_organizer_may_edit_but_not_switch_demo(client, conversation, participant):
    _organizer(client, conversation, participant)

    caps = client.get(_endpoint(conversation)).get_json()['data']['capabilities']

    assert caps == {'edit': True, 'switchDemo': False}


def test_moderator_may_neither_edit_nor_switch_demo(client, conversation, participant):
    db.session.add(AdminRole(
        participant_id=participant.id, conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')

    caps = client.get(_endpoint(conversation)).get_json()['data']['capabilities']

    assert caps == {'edit': False, 'switchDemo': False}


def test_site_admin_sees_the_switch_demo_capability(admin_client, conversation):
    caps = admin_client.get(_endpoint(conversation)).get_json()['data']['capabilities']
    assert caps == {'edit': True, 'switchDemo': True}


# ── creation ────────────────────────────────────────────────────────────────


def test_new_demo_consultation_stores_the_fixed_answers(admin_client):
    response = admin_client.post('/api/v1/admin/conversations', json={
        'slug': 'new-demo', 'title': 'New demo', 'introHtml': '', 'outroHtml': '',
        'accessPolicy': 'demo', 'phaseRoute': 'default_7',
        'eligibilityEventId': '', 'eligibilityLabel': '', 'polisId': 'dem1234567',
    })

    assert response.status_code == 201
    conversation = Conversation.query.filter_by(slug='new-demo').one()
    assert _stored(conversation) == FIXED
