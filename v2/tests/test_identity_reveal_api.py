"""Identity-reveal application service and browser API contract tests."""

import json
from datetime import datetime, timedelta, timezone

from db import Participation, db


def _join_closed(participant, conversation, *, days_ago: int = 45):
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='quiet-otter',
    )
    db.session.add(participation)
    db.session.commit()
    return participation


def test_identity_reveal_read_exposes_timeline_and_server_capability(
    auth_client, participant, conversation,
):
    _join_closed(participant, conversation)

    response = auth_client.get(
        '/api/v1/conversations/test-conv/identity-reveal',
    )

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['state'] == 'open'
    assert data['pseudonym'] == 'quiet-otter'
    assert data['wikimediaUsername'] == 'testuser'
    assert data['publicUsername'] is None
    assert data['capabilities'] == {'revealIdentity': True}
    assert data['timeline']['closedAt'].endswith('Z')
    assert data['timeline']['opensAt'].endswith('Z')
    assert data['timeline']['closesAt'].endswith('Z')
    assert data['timeline']['nextBoundaryAt'].endswith('Z')
    assert data['links']['about'] == '/app/conversations/test-conv/about'
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert str(participant.mw_user_id) not in serialized


def test_identity_reveal_command_is_irreversible_and_idempotent(
    auth_client, participant, conversation,
):
    participation = _join_closed(participant, conversation)

    first = auth_client.post(
        '/api/v1/conversations/test-conv/identity-reveal',
        json={'confirm': True},
    )
    replay = auth_client.post(
        '/api/v1/conversations/test-conv/identity-reveal',
        json={'confirm': True},
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.get_json()['data']['state'] == 'revealed'
    assert replay.get_json()['data']['state'] == 'revealed'
    assert replay.get_json()['data']['publicUsername'] == 'testuser'
    db.session.refresh(participation)
    assert participation.public_username == 'testuser'
    assert participation.revealed_at is not None


def test_identity_reveal_command_rejects_closed_window_with_typed_state(
    auth_client, participant, conversation,
):
    participation = _join_closed(participant, conversation, days_ago=10)

    response = auth_client.post(
        '/api/v1/conversations/test-conv/identity-reveal',
        json={'confirm': True},
    )

    assert response.status_code == 409
    assert response.get_json()['error'] == {
        'code': 'identity_reveal_unavailable',
        'message': 'Identity reveal is not available in the current timeline state.',
        'details': {'state': 'pending'},
    }
    db.session.refresh(participation)
    assert participation.public_username is None


def test_identity_reveal_requires_explicit_true_confirmation(
    auth_client, participant, conversation,
):
    participation = _join_closed(participant, conversation)

    response = auth_client.post(
        '/api/v1/conversations/test-conv/identity-reveal',
        json={'confirm': False},
    )

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_failed'
    db.session.refresh(participation)
    assert participation.public_username is None


def test_identity_reveal_requires_authentication(client, conversation):
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.session.commit()

    response = client.get('/api/v1/conversations/test-conv/identity-reveal')

    assert response.status_code == 401


def test_identity_reveal_requires_participation(
    auth_client, conversation,
):
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/identity-reveal')

    assert response.status_code == 409


def test_openapi_documents_identity_reveal_read_and_idempotent_command(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    path = spec['paths']['/conversations/{slug}/identity-reveal']

    assert path['get']['operationId'] == 'getIdentityReveal'
    assert path['post']['operationId'] == 'createIdentityReveal'
    assert 'idempotent' in path['post']['description'].lower()
    assert spec['components']['schemas']['CreateIdentityRevealRequest'][
        'properties'
    ]['confirm']['const'] is True
