"""Participant-safe read contracts for moderation history and output pages."""

import json
from datetime import datetime, timezone

from db import AuditEvent, Participation, db


def _join(conversation, participant, pseudonym='quiet-otter'):
    participation = Participation(
        conversation_id=conversation.id,
        participant_id=participant.id,
        pseudonym=pseudonym,
    )
    db.session.add(participation)
    db.session.commit()
    return participation


def test_public_moderation_log_is_empty_without_events(client, conversation):
    response = client.get('/api/v1/conversations/test-conv/moderation-log')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.get_json()['data'] == {
        'slug': 'test-conv',
        'title': 'Test Conversation',
        'events': [],
        'links': {
            'self': '/api/v1/conversations/test-conv/moderation-log',
            'conversation': '/c/test-conv',
            'about': '/c/test-conv/about',
        },
    }


def test_public_moderation_log_excludes_ids_and_private_notes(
    client, conversation, participant, admin_participant,
):
    _join(conversation, participant)
    db.session.add(AuditEvent(
        ts=datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc),
        actor_participant_id=admin_participant.id,
        conversation_id=conversation.id,
        operation='participant.ban',
        target_type='participant',
        target_id=str(participant.id),
        detail={'summary': 'private moderator note'},
    ))
    db.session.commit()

    data = client.get(
        '/api/v1/conversations/test-conv/moderation-log',
    ).get_json()['data']

    assert data['events'] == [{
        'occurredAt': '2026-08-14T09:30:00Z',
        'action': 'Banned',
        'pseudonym': 'quiet-otter',
        'scope': 'conversation',
        'actor': 'adminuser',
        'actorKind': None,
    }]
    serialized = json.dumps(data)
    assert 'private moderator note' not in serialized
    assert participant.xid not in serialized


def test_public_moderation_log_sends_null_for_unknown_names(client, conversation):
    """An unknown participant or moderator is null, never an English placeholder.

    Catches the server filling the gap with 'participant' or 'administrator', which the
    page would then show untranslated.
    """
    db.session.add(AuditEvent(
        ts=datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc),
        actor_participant_id=None,
        conversation_id=conversation.id,
        operation='participant.unban',
        target_type='participant',
        target_id='424242',
    ))
    db.session.commit()

    events = client.get(
        '/api/v1/conversations/test-conv/moderation-log',
    ).get_json()['data']['events']

    assert events == [{
        'occurredAt': '2026-08-14T09:30:00Z',
        'action': 'Unbanned',
        'pseudonym': None,
        'scope': 'conversation',
        'actor': None,
        'actorKind': None,
    }]


def test_public_moderation_log_marks_a_ban_by_a_site_admin_without_an_account(
    client, conversation, participant,
):
    """An env-listed admin has no Participant row; the log says so instead of 'unknown'.

    Catches actorKind being dropped, which would show a site administrator's ban as made by
    an unknown moderator.
    """
    _join(conversation, participant, pseudonym='')
    db.session.add(AuditEvent(
        ts=datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc),
        actor_participant_id=None,
        conversation_id=conversation.id,
        operation='participant.ban',
        target_type='participant',
        target_id=str(participant.id),
        detail={'actor_kind': 'env_admin', 'scope': 'conversation'},
    ))
    db.session.commit()

    events = client.get(
        '/api/v1/conversations/test-conv/moderation-log',
    ).get_json()['data']['events']

    # The empty pseudonym also comes back as null, so the page shows its fallback.
    assert events == [{
        'occurredAt': '2026-08-14T09:30:00Z',
        'action': 'Banned',
        'pseudonym': None,
        'scope': 'conversation',
        'actor': None,
        'actorKind': 'site_admin',
    }]


def test_output_contract_requires_authentication(client, conversation):
    response = client.get(
        '/api/v1/conversations/test-conv/outputs/initial-clustering',
    )

    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'unauthorized'


def test_output_contract_requires_participation(
    auth_client, participant, conversation,
):
    response = auth_client.get(
        '/api/v1/conversations/test-conv/outputs/initial-clustering',
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'conflict'


def test_output_contract_projects_ready_context(
    auth_client, participant, conversation,
):
    _join(conversation, participant)
    conversation.phase_argument_mapping = True
    db.session.commit()

    response = auth_client.get(
        '/api/v1/conversations/test-conv/outputs/initial-clustering',
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['slug'] == 'test-conv'
    assert data['title'] == 'Test Conversation'
    assert data['output']['key'] == 'initial-clustering'
    assert data['output']['label'] == 'Initial clustering'
    assert data['output']['phase'] == 'Explore'
    assert data['output']['status'] == 'provisional'
    assert data['output']['ready'] is True
    assert 'Polis clustering' in data['output']['method']
    assert data['links'] == {
        'self': '/api/v1/conversations/test-conv/outputs/initial-clustering',
        'conversation': '/c/test-conv',
        'about': '/c/test-conv/about',
    }


def test_output_contract_rejects_unknown_output(
    auth_client, participant, conversation,
):
    """404 for an unknown output key — and 200 for a known one on the same route.

    The negative half alone is vacuous: it would pass just as well if the endpoint
    had been deleted, which is how a whole-suite mutation of the /api/v1/ prefix
    left this test green. The positive probe is what distinguishes 'rejects this
    output key' from 'route absent'.
    """
    _join(conversation, participant)
    conversation.phase_argument_mapping = True
    db.session.commit()

    response = auth_client.get(
        '/api/v1/conversations/test-conv/outputs/not-real',
    )

    assert response.status_code == 404

    known = auth_client.get(
        '/api/v1/conversations/test-conv/outputs/initial-clustering',
    )

    assert known.status_code == 200
    assert known.get_json()['data']['output']['key'] == 'initial-clustering'


def test_openapi_describes_public_read_operations(client):
    paths = client.get('/api/v1/openapi.json').get_json()['paths']

    assert paths['/conversations/{slug}/moderation-log']['get']['operationId'] == (
        'getModerationLog'
    )
    assert paths['/conversations/{slug}/outputs/{outputKey}']['get']['operationId'] == (
        'getConversationOutput'
    )
