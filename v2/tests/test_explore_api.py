"""Explore-phase read and vote API contract tests."""

import json
from unittest.mock import MagicMock, patch

from db import Participation, db
from services.explore import build_explore_state


def _response(payload=None, *, status=200, cookies=None):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.content = b'{}' if payload is not None else b''
    response.json.return_value = payload or {}
    response.cookies = cookies or {}
    return response


def _join(participant, conversation):
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='explore-otter',
    )
    db.session.add(participation)
    conversation.phase_submission = True
    db.session.commit()
    return participation


def test_explore_projection_prioritises_seed_and_hides_completed_statements():
    state = build_explore_state(
        statements_payload={
            '3': {'id': 3, 'text': 'Community statement'},
            '2': {'id': 2, 'text': 'Seed statement', 'is_seed': True},
            '1': {'id': 1, 'text': 'Meta statement', 'is_meta': True},
        },
        participant_payload={'votes': [1], 'statements': []},
        ordering_key='stable-participant',
        new_statement_unlock_at=10,
        new_statement_max=3,
        new_statements_used=1,
    )

    assert state['currentStatement']['id'] == 2
    assert state['progress'] == {
        'completed': 1, 'total': 3, 'remaining': 2, 'allDone': False,
    }
    assert state['newStatement'] == {
        'unlocked': False,
        'unlockAfter': 3,
        'quota': 3,
        'used': 1,
        'remaining': 2,
    }


def test_explore_api_owns_upstream_session_and_returns_privacy_safe_state(
    auth_client, participant, conversation, app,
):
    _join(participant, conversation)
    app.config['PARTICIAPI_SUB_SECRET'] = 'shared-upstream-secret'
    session_response = _response(
        {'csrf_token': 'upstream-csrf'}, cookies={'session': 'upstream-cookie'},
    )
    statement_response = _response({
        '10': {'id': 10, 'text': 'A seed question', 'is_seed': True},
        '11': {'id': 11, 'text': 'Another question'},
    })
    participant_response = _response({'votes': [10], 'statements': []})

    with (
        patch('app.polis_http.post', return_value=session_response) as post,
        patch('app.polis_http.get', side_effect=[
            statement_response, participant_response,
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['currentStatement'] == {
        'id': 11,
        'text': 'Another question',
        'isMeta': False,
        'isSeed': False,
    }
    assert data['progress'] == {
        'completed': 1, 'total': 2, 'remaining': 1, 'allDone': False,
    }
    assert data['capabilities']['vote'] is True
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert conversation.polis_id not in serialized
    assert 'upstream-cookie' not in serialized
    assert 'upstream-csrf' not in serialized

    assert post.call_args.kwargs['headers']['X-Particiapi-Sub-Secret'] == 'shared-upstream-secret'
    assert post.call_args.kwargs['headers']['X-Particiapi-Sub'] != participant.xid
    with auth_client.session_transaction() as browser_session:
        stored = browser_session['particiapi_api_sessions'][str(conversation.id)]
    assert stored == {
        'cookie': 'upstream-cookie', 'csrfToken': 'upstream-csrf',
    }


def test_explore_vote_is_idempotent_put_and_translates_agree_sign(
    auth_client, participant, conversation,
):
    participation = _join(participant, conversation)
    with auth_client.session_transaction() as browser_session:
        browser_session['particiapi_api_sessions'] = {
            str(conversation.id): {
                'cookie': 'existing-cookie', 'csrfToken': 'existing-csrf',
            },
        }
    statements = _response({'7': {'id': 7, 'text': 'Vote on this'}})
    upstream_participant = _response({'votes': [], 'statements': []})

    with (
        patch('app.polis_http.post') as bootstrap,
        patch('app.polis_http.get', side_effect=[
            statements, upstream_participant,
        ]),
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        response = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'agree'},
        )

    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'statementId': 7,
        'choice': 'agree',
        'links': {'explore': '/api/v1/conversations/test-conv/explore'},
    }
    bootstrap.assert_not_called()
    assert put.call_args.kwargs['json'] == {'value': -1}
    assert put.call_args.kwargs['cookies'] == {'session': 'existing-cookie'}
    assert put.call_args.kwargs['headers']['X-CSRF-Token'] == 'existing-csrf'
    db.session.refresh(participation)
    assert participation.last_engagement is not None


def test_explore_vote_rejects_statement_from_another_conversation(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    session_response = _response(
        {'csrf_token': 'csrf'}, cookies={'session': 'cookie'},
    )
    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', side_effect=[
            _response({'7': {'id': 7, 'text': 'Known'}}),
            _response({'votes': [], 'statements': []}),
        ]),
        patch('app.polis_http.put') as put,
    ):
        response = auth_client.put(
            '/api/v1/conversations/test-conv/statements/99/vote',
            json={'choice': 'pass'},
        )

    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'
    put.assert_not_called()


def test_explore_api_returns_typed_upstream_failure(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    with patch(
        'app.polis_http.post', return_value=_response({}, status=503),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'upstream_unavailable'


def test_explore_api_rejects_malformed_upstream_payload(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    with (
        patch('app.polis_http.post', return_value=_response(
            {'csrf_token': 'csrf'}, cookies={'session': 'cookie'},
        )),
        patch('app.polis_http.get', side_effect=[
            _response(['not', 'a', 'statement-map']),
            _response({'votes': [], 'statements': []}),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'upstream_unavailable'


def test_explore_api_rejects_closed_phase_before_upstream_call(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    conversation.phase_submission = False
    db.session.commit()

    with patch('app.polis_http.post') as post:
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'conflict'
    post.assert_not_called()


def test_openapi_documents_idempotent_explore_vote(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths'][
        '/conversations/{slug}/statements/{statementId}/vote'
    ]['put']

    assert operation['operationId'] == 'putExploreVote'
    assert 'Idempotent' in operation['description']
    assert spec['paths']['/conversations/{slug}/explore']['get'][
        'operationId'
    ] == 'getExploreState'
