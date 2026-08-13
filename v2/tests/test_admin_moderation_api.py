"""Admin moderation queue and resolution API contract tests."""

import json
from unittest.mock import patch

from db import (Argument, AuditEvent, ContentFlag, FeaturedStatement,
                Participation, db)
from polis_admin import PolisParticipantError


def _participation(conversation, participant):
    row = Participation(
        conversation_id=conversation.id,
        participant_id=participant.id,
        pseudonym='private-reporter',
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_admin_flag_queue_exposes_targets_without_reporter_identity(
    admin_client, conversation, participant,
):
    _participation(conversation, participant)
    featured = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=9,
        statement_text='Featured statement',
        confirmed_by_admin=True,
    )
    db.session.add(featured)
    db.session.flush()
    argument = Argument(
        featured_statement_id=featured.id,
        proposer_pseudonym='another-person',
        body='An argument requiring review.',
        side='pro',
    )
    db.session.add(argument)
    db.session.flush()
    db.session.add_all([
        ContentFlag(
            conversation_id=conversation.id,
            participant_id=participant.id,
            content_type='statement',
            statement_tid=12,
            category='privacy',
            detail='Contains identifying details.',
            status='open',
        ),
        ContentFlag(
            conversation_id=conversation.id,
            participant_id=participant.id,
            content_type='argument',
            argument_id=argument.id,
            category='off_topic',
            status='open',
        ),
    ])
    db.session.commit()

    with patch('app._statement_text_map', return_value={12: 'Private statement'}):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/flags',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['dataAvailability'] == {'statementText': True}
    assert {row['target']['text'] for row in data['open']} == {
        'Private statement', 'An argument requiring review.',
    }
    assert {row['categoryLabel'] for row in data['open']} == {
        'Privacy violation', 'Off-topic',
    }
    serialized = json.dumps(data)
    assert 'private-reporter' not in serialized
    assert participant.xid not in serialized
    assert 'participantId' not in serialized


def test_admin_flag_queue_remains_actionable_when_statement_text_is_unavailable(
    admin_client, conversation,
):
    flag = ContentFlag(
        conversation_id=conversation.id,
        content_type='statement',
        statement_tid=12,
        category='other',
        detail='Needs review.',
        status='open',
    )
    db.session.add(flag)
    db.session.commit()

    with patch(
        'app._statement_text_map',
        side_effect=PolisParticipantError('upstream unavailable'),
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/flags',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['dataAvailability'] == {'statementText': False}
    assert data['open'][0]['target']['text'] == 'Statement text unavailable'
    assert data['open'][0]['id'] == flag.id


def test_admin_flag_queue_requires_moderation_access(
    auth_client, conversation,
):
    response = auth_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/flags',
    )

    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'


def test_admin_flag_resolution_is_idempotent_and_audited_once(
    admin_client, conversation,
):
    flag = ContentFlag(
        conversation_id=conversation.id,
        content_type='statement',
        statement_tid=12,
        category='privacy',
        status='open',
    )
    db.session.add(flag)
    db.session.commit()
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}'
        f'/flags/{flag.id}/resolution'
    )

    first = admin_client.put(endpoint, json={
        'resolved': True,
        'note': '<b>Removed identifying details</b>',
    })
    replay = admin_client.put(endpoint, json={
        'resolved': True,
        'note': 'Should not replace the original note',
    })

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    assert replay.get_json()['data']['resolution']['note'] == (
        'Removed identifying details'
    )
    db.session.refresh(flag)
    assert flag.status == 'resolved'
    assert flag.resolution_note == 'Removed identifying details'
    assert [event.operation for event in AuditEvent.query.all()] == [
        'content_flag.resolve',
    ]


def test_admin_flag_resolution_validates_and_scopes_target(
    admin_client, conversation,
):
    invalid = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/flags/999/resolution',
        json={'resolved': False},
    )
    missing = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/flags/999/resolution',
        json={'resolved': True},
    )

    assert invalid.status_code == 400
    assert invalid.get_json()['error']['code'] == 'validation_failed'
    assert missing.status_code == 404


def test_openapi_documents_admin_moderation_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    queue_path = '/admin/conversations/{conversationId}/flags'
    resolution_path = (
        '/admin/conversations/{conversationId}/flags/{flagId}/resolution'
    )

    assert spec['paths'][queue_path]['get']['operationId'] == (
        'getAdminConversationFlags'
    )
    assert spec['paths'][resolution_path]['put']['operationId'] == (
        'putAdminFlagResolution'
    )
    flag = spec['components']['schemas']['AdminContentFlag']['properties']
    assert 'reporter' not in flag
    assert 'participantId' not in flag
