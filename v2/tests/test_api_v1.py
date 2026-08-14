"""Contract tests for the versioned browser API kernel."""

import json

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from db import Conversation, Participant, Participation, db


def test_session_contract_for_anonymous_browser(client):
    response = client.get('/api/v1/session')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['state'] == 'anonymous'
    assert data['user'] is None
    assert data['capabilities'] == {'administerSite': False}
    assert data['csrfToken']
    assert data['developerLogins'] == []
    assert data['links'] == {'login': '/login', 'logout': '/logout'}


def test_session_contract_for_authenticated_participant(auth_client, participant):
    payload = auth_client.get('/api/v1/session').get_json()

    assert payload['data']['state'] == 'authenticated'
    assert payload['data']['user'] == {'username': 'testuser', 'emailable': True}
    assert payload['data']['capabilities'] == {'administerSite': False}
    serialized = json.dumps(payload)
    assert participant.xid not in serialized
    assert str(participant.mw_user_id) not in serialized


def test_session_contract_exposes_capability_not_role_logic(admin_client):
    data = admin_client.get('/api/v1/session').get_json()['data']

    assert data['state'] == 'authenticated'
    assert data['capabilities'] == {'administerSite': True}


def test_session_contract_for_demo_guest(client):
    guest = Participant(
        mw_user_id=-1_000_000_001,
        mw_username='Demo-guest-contract',
        xid='d' * 64,
        is_demo=True,
    )
    db.session.add(guest)
    db.session.commit()
    with client.session_transaction() as sess:
        sess['xid'] = guest.xid
        sess['demo_conversation_id'] = 1

    data = client.get('/api/v1/session').get_json()['data']
    assert data['state'] == 'demo'
    assert data['user'] is None
    assert data['capabilities'] == {'administerSite': False}


def test_unknown_api_route_uses_structured_error_contract(client):
    response = client.get('/api/v1/not-a-route')

    assert response.status_code == 404
    assert response.get_json() == {
        'error': {
            'code': 'not_found',
            'message': 'The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.',
        },
    }


def test_openapi_document_is_served_and_describes_session(client):
    response = client.get('/api/v1/openapi.json')

    assert response.status_code == 200
    spec = response.get_json()
    assert spec['openapi'] == '3.1.0'
    assert spec['paths']['/session']['get']['operationId'] == 'getSession'


def test_anonymous_conversation_lane_exposes_public_contract_without_internal_ids(
    client, conversation,
):
    response = client.get('/api/v1/conversations?space=real')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['space'] == 'real'
    assert data['authenticated'] is False
    card = data['groups']['available'][0]
    assert card['slug'] == conversation.slug
    assert card['capabilities'] == {
        'join': False, 'participate': False, 'moderate': False,
    }
    serialized = json.dumps(data)
    assert conversation.polis_id not in serialized
    assert 'conversation_id' not in serialized


def test_authenticated_lane_uses_participant_workload_projection(
    auth_client, participant, conversation,
):
    conversation.phase_submission = True
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='api-otter',
    ))
    db.session.commit()

    with patch(
        'app.PolisServerClient.get_statements_remaining_bulk',
        return_value={conversation.polis_id: 0},
    ):
        data = auth_client.get('/api/v1/conversations').get_json()['data']

    card = data['groups']['caughtUp'][0]
    assert card['participantState'] == 'caught_up'
    assert card['pseudonym'] == 'api-otter'
    assert card['statementsRemaining'] == 0
    assert card['capabilities']['participate'] is True
    assert card['links']['self'] == '/c/test-conv'
    assert card['links']['about'] == '/c/test-conv/about'
    assert card['links']['explore'] == '/app/conversations/test-conv/explore'
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert str(participant.mw_user_id) not in serialized


def test_conversation_lane_exposes_scheduled_transition_as_utc(
    client, conversation,
):
    conversation.scheduled_transition_at = datetime(2026, 8, 20, 14, 30)
    conversation.scheduled_transition_target = 'argument_mapping'
    db.session.commit()

    card = client.get('/api/v1/conversations').get_json()['data']['groups']['available'][0]

    assert card['scheduledTransition'] == {
        'at': '2026-08-20T14:30:00Z',
        'target': 'argument_mapping',
        'targetLabel': 'Arguments',
    }


def test_closed_joined_conversation_advertises_identity_reveal_route(
    auth_client, participant, conversation,
):
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='api-otter',
    ))
    db.session.commit()

    card = auth_client.get('/api/v1/conversations').get_json()['data'][
        'groups'
    ]['archived'][0]

    assert card['links']['identityReveal'] == (
        '/app/conversations/test-conv/identity-reveal'
    )


def test_conversation_lane_rejects_unknown_space(client):
    response = client.get('/api/v1/conversations?space=production')

    assert response.status_code == 400
    assert response.get_json() == {
        'error': {
            'code': 'validation_failed',
            'message': 'The requested conversation space is invalid.',
            'details': {'fields': {'space': ['Choose real or demo.']}},
        },
    }
