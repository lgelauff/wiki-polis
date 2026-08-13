"""Explore-phase read and vote API contract tests."""

import json
from unittest.mock import MagicMock, patch

import requests

from db import (CommandReceipt, Participation, StatementPassSignal,
                StatementProvenance, StatementSimilarityScore, db)
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
    conversation.phase_argument_mapping = True
    db.session.commit()
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
    assert data['links']['arguments'] == '/app/conversations/test-conv/arguments'
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
        'passReason': None,
        'links': {'explore': '/api/v1/conversations/test-conv/explore'},
    }
    bootstrap.assert_not_called()
    assert put.call_args.kwargs['json'] == {'value': -1}
    assert put.call_args.kwargs['cookies'] == {'session': 'existing-cookie'}
    assert put.call_args.kwargs['headers']['X-CSRF-Token'] == 'existing-csrf'
    db.session.refresh(participation)
    assert participation.last_engagement is not None


def test_explore_pass_reason_is_created_updated_preserved_and_cleared(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    _store_upstream_session(auth_client, conversation)
    statements = {'7': {'id': 7, 'text': 'Vote on this'}}

    with (
        patch('app.polis_http.get', side_effect=[
            _response(statements), _response({'votes': [], 'statements': []}),
            _response(statements), _response({'votes': [], 'statements': []}),
            _response(statements), _response({'votes': [], 'statements': []}),
            _response(statements), _response({'votes': [], 'statements': []}),
        ]),
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        created = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'pass', 'passReason': 'unsure'},
        )
        updated = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'pass', 'passReason': 'confusing'},
        )
        replayed = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'pass'},
        )
        cleared = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'disagree'},
        )

    assert created.get_json()['data']['passReason'] == 'unsure'
    assert updated.get_json()['data']['passReason'] == 'confusing'
    assert replayed.get_json()['data']['passReason'] == 'confusing'
    assert cleared.get_json()['data']['passReason'] is None
    assert StatementPassSignal.query.count() == 0
    assert [call.kwargs['json'] for call in put.call_args_list] == [
        {'value': 0}, {'value': 0}, {'value': 0}, {'value': 1},
    ]


def test_explore_vote_rejects_pass_reason_for_non_pass_choice(
    auth_client, participant, conversation,
):
    _join(participant, conversation)

    with patch('app.polis_http.put') as put:
        response = auth_client.put(
            '/api/v1/conversations/test-conv/statements/7/vote',
            json={'choice': 'agree', 'passReason': 'confusing'},
        )

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_failed'
    put.assert_not_called()


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
    request_schema = spec['components']['schemas']['ExploreVoteRequest']
    receipt_schema = spec['components']['schemas']['ExploreVoteReceipt']
    assert request_schema['properties']['passReason']['enum'] == [
        'unsure', 'confusing',
    ]
    assert 'passReason' in receipt_schema['required']
    assert spec['paths']['/conversations/{slug}/explore']['get'][
        'operationId'
    ] == 'getExploreState'


def _store_upstream_session(client, conversation):
    with client.session_transaction() as browser_session:
        browser_session['particiapi_api_sessions'] = {
            str(conversation.id): {
                'cookie': 'existing-cookie', 'csrfToken': 'existing-csrf',
            },
        }


def test_statement_command_creates_once_and_replays_completed_receipt(
    auth_client, participant, conversation,
):
    participation = _join(participant, conversation)
    _store_upstream_session(auth_client, conversation)

    with patch(
        'app.polis_http.post', return_value=_response({'id': 41}, status=201),
    ) as post:
        first = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': '  A clearer shared claim.  '},
            headers={'Idempotency-Key': 'statement-key-41'},
        )
        replay = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'A clearer shared claim.'},
            headers={'Idempotency-Key': 'statement-key-41'},
        )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.get_json() == replay.get_json()
    assert first.get_json()['data'] == {
        'statementId': 41,
        'kind': 'new',
        'derivedFromStatementId': None,
        'newStatementQuotaRemaining': 2,
        'links': {'explore': '/api/v1/conversations/test-conv/explore'},
    }
    post.assert_called_once()
    assert post.call_args.kwargs['json'] == {'text': 'A clearer shared claim.'}
    db.session.refresh(participation)
    assert participation.new_stmt_ids == [41]
    receipt = CommandReceipt.query.one()
    assert receipt.state == 'completed'
    assert receipt.response['statementId'] == 41


def test_statement_command_rejects_key_reuse_with_changed_body(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    _store_upstream_session(auth_client, conversation)
    with patch(
        'app.polis_http.post', return_value=_response({'id': 42}, status=201),
    ) as post:
        auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'First claim'},
            headers={'Idempotency-Key': 'statement-key-42'},
        )
        conflict = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'Changed claim'},
            headers={'Idempotency-Key': 'statement-key-42'},
        )

    assert conflict.status_code == 409
    assert conflict.get_json()['error']['code'] == 'idempotency_conflict'
    post.assert_called_once()


def test_statement_command_blocks_retry_after_ambiguous_upstream_failure(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    _store_upstream_session(auth_client, conversation)
    with patch('app.polis_http.post', side_effect=requests.Timeout) as post:
        failed = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'Possibly accepted claim'},
            headers={'Idempotency-Key': 'statement-key-43'},
        )
        retry = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'Possibly accepted claim'},
            headers={'Idempotency-Key': 'statement-key-43'},
        )

    assert failed.status_code == 502
    assert retry.status_code == 409
    assert failed.get_json()['error']['code'] == 'command_outcome_unknown'
    assert retry.get_json()['error']['code'] == 'command_outcome_unknown'
    post.assert_called_once()
    assert CommandReceipt.query.one().state == 'pending'


def test_statement_command_releases_receipt_when_session_bootstrap_fails(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    with patch(
        'app.polis_http.post', return_value=_response({}, status=503),
    ):
        response = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'Safe to retry claim'},
            headers={'Idempotency-Key': 'statement-key-44'},
        )

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'upstream_unavailable'
    assert CommandReceipt.query.count() == 0


def test_derivative_statement_records_provenance_without_consuming_quota(
    auth_client, participant, conversation,
):
    participation = _join(participant, conversation)
    participation.new_stmt_ids = [5]
    db.session.commit()
    _store_upstream_session(auth_client, conversation)

    with (
        patch('app._statement_text_map', return_value={7: 'Original claim'}),
        patch('app._statement_similarity_scores', return_value={
            'char': 0.88, 'semantic-v1': 0.91,
        }),
        patch(
            'app.polis_http.post', return_value=_response({'id': 45}, status=201),
        ),
    ):
        response = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={
                'text': 'Clearer original claim',
                'derivedFromStatementId': 7,
            },
            headers={'Idempotency-Key': 'statement-key-45'},
        )

    assert response.status_code == 201
    assert response.get_json()['data']['kind'] == 'derivative'
    provenance = StatementProvenance.query.one()
    assert (provenance.polis_statement_id, provenance.derived_from_tid) == (45, 7)
    assert {
        score.model: score.value
        for score in StatementSimilarityScore.query.all()
    } == {'char': 0.88, 'semantic-v1': 0.91}
    db.session.refresh(participation)
    assert participation.new_stmt_ids == [5]


def test_openapi_documents_idempotent_statement_command(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/conversations/{slug}/statements']['post']

    assert operation['operationId'] == 'createStatement'
    idempotency = next(
        parameter for parameter in operation['parameters']
        if parameter['name'] == 'Idempotency-Key'
    )
    assert idempotency['required'] is True
    assert {'200', '201', '409', '502'} <= set(operation['responses'])
