"""Admin participant roster and access-command API contract tests."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from db import (AdminRole, Argument, ArgumentVote, AuditEvent, Conversation,
                ConversationBan, FeaturedStatement, Participant, Participation, db)
from tests.conftest import login


def _join(conversation, participant, *, pseudonym='steady-lion'):
    participation = Participation(
        conversation_id=conversation.id,
        participant_id=participant.id,
        pseudonym=pseudonym,
        last_engagement=datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc),
    )
    db.session.add(participation)
    db.session.commit()
    return participation


def test_admin_roster_api_uses_shared_scoped_engagement_projection(
    app, admin_client, conversation, participant,
):
    app.config['POLIS_DATABASE_URL'] = 'postgres://stats.example/db'
    app.config['PARTICIAPI_SUB_SECRET'] = 'subject-secret'
    participation = _join(conversation, participant)
    featured = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=7,
        statement_text='Featured',
        confirmed_by_admin=True,
    )
    db.session.add(featured)
    db.session.flush()
    argument = Argument(
        featured_statement_id=featured.id,
        proposer_pseudonym=participation.pseudonym,
        body='Useful because...',
        side='pro',
    )
    db.session.add(argument)
    db.session.flush()
    db.session.add(ArgumentVote(
        argument_id=argument.id,
        participant_id=participant.id,
    ))
    db.session.commit()
    server = MagicMock()
    server.get_statement_progress_for_participants.return_value = {
        'scoped-subject': {'total': 5, 'voted': 3, 'remaining': 2},
    }

    with (
        patch('app._polis_server_client', return_value=server),
        patch('app._conversation_subject', return_value='scoped-subject'),
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/participants',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['conversation'] == {
        'id': conversation.id,
        'slug': conversation.slug,
        'title': conversation.title,
    }
    assert data['dataAvailability'] == {'statementProgress': True}
    assert data['participants'] == [{
        'participantId': participant.id,
        'username': 'testuser',
        'pseudonym': 'steady-lion',
        'statementProgress': {'total': 5, 'voted': 3, 'remaining': 2},
        'arguments': {'submitted': 1, 'prioritized': 1},
        'lastEngagementAt': '2026-08-13T09:30:00Z',
        'access': {'banned': False, 'changedAt': None, 'summary': None},
    }]
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert conversation.polis_id not in serialized
    assert 'scoped-subject' not in serialized


def test_admin_roster_api_requires_conversation_moderation_access(
    auth_client, conversation, participant,
):
    _join(conversation, participant)

    response = auth_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/participants',
    )

    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'


def test_conversation_moderator_can_read_admin_roster(
    client, conversation, participant,
):
    _join(conversation, participant)
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, participant.mw_username)

    response = client.get(
        f'/api/v1/admin/conversations/{conversation.id}/participants',
    )

    assert response.status_code == 200
    assert response.get_json()['data']['capabilities'] == {
        'setParticipantAccess': True,
    }


def test_admin_access_command_is_idempotent_and_audits_only_changes(
    admin_client, conversation, participant,
):
    _join(conversation, participant)
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}'
        f'/participants/{participant.id}/access'
    )

    first = admin_client.put(endpoint, json={
        'banned': True,
        'summary': '<b>Repeated disruption</b>',
    })
    replay = admin_client.put(endpoint, json={
        'banned': True,
        'summary': 'This replay does not overwrite the original reason',
    })
    lifted = admin_client.put(endpoint, json={
        'banned': False,
        'summary': 'Issue resolved',
    })
    lifted_replay = admin_client.put(endpoint, json={'banned': False})

    assert first.status_code == replay.status_code == 200
    assert lifted.status_code == lifted_replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert first.get_json()['data']['summary'] == 'Repeated disruption'
    assert replay.get_json()['data']['changed'] is False
    assert replay.get_json()['data']['summary'] == 'Repeated disruption'
    assert lifted.get_json()['data']['changed'] is True
    assert lifted.get_json()['data']['banned'] is False
    assert lifted_replay.get_json()['data']['changed'] is False
    ban = ConversationBan.query.one()
    assert ban.lifted_at is not None
    assert ban.lift_summary == 'Issue resolved'
    assert [event.operation for event in AuditEvent.query.order_by(AuditEvent.id)] == [
        'participant.ban', 'participant.unban',
    ]


def test_admin_access_command_rejects_invalid_and_cross_conversation_targets(
    admin_client, conversation, participant,
):
    other = Conversation(
        slug='other-conv', polis_id='other12345', title='Other', active=True,
        access_policy='public',
    )
    db.session.add(other)
    db.session.flush()
    _join(other, participant, pseudonym='other-lion')
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}'
        f'/participants/{participant.id}/access'
    )

    invalid = admin_client.put(endpoint, json={'banned': 'yes'})
    missing = admin_client.put(endpoint, json={'banned': True})

    assert invalid.status_code == 400
    assert invalid.get_json()['error']['code'] == 'validation_failed'
    assert missing.status_code == 404
    assert ConversationBan.query.count() == 0


def test_openapi_documents_admin_participant_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    roster_path = '/admin/conversations/{conversationId}/participants'
    access_path = (
        '/admin/conversations/{conversationId}/participants/'
        '{participantId}/access'
    )

    assert spec['paths'][roster_path]['get']['operationId'] == (
        'getAdminConversationParticipants'
    )
    assert spec['paths'][access_path]['put']['operationId'] == (
        'putAdminParticipantAccess'
    )
    access = spec['components']['schemas']['AdminParticipant']['properties']['access']
    assert access['$ref'] == '#/components/schemas/AdminParticipantAccess'
