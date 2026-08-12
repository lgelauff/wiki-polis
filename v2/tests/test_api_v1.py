"""Contract tests for the versioned browser API kernel."""

import json

from db import Participant, db


def test_session_contract_for_anonymous_browser(client):
    response = client.get('/api/v1/session')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['state'] == 'anonymous'
    assert data['user'] is None
    assert data['capabilities'] == {'administerSite': False}
    assert data['csrfToken']
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
