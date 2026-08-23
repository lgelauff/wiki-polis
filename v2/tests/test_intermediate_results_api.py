"""Intermediate-results HTTP contract tests."""

import json
from unittest.mock import patch

from db import db


def _results():
    return {
        'majority': {
            'agree': [{'statement_text': 'Shared maintenance matters', 'value': .82}],
            'disagree': [{'statement_text': 'Centralize every budget', 'value': .64}],
        },
        'groups': [{
            'agree': [{'statement_text': 'Local autonomy matters', 'value': .76}],
            'disagree': [],
        }],
        'conversation_id': 'private-upstream-id',
    }


def test_intermediate_results_api_projects_ready_state(client, conversation):
    conversation.phase_public_results = True
    db.session.commit()

    with patch(
        'app._load_intermediate_results',
        return_value=(_results(), {'n_participants': 12}, False),
    ):
        response = client.get(
            '/api/v1/conversations/test-conv/intermediate-results',
        )

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['state'] == 'ready'
    assert data['participantCount'] == 12
    assert data['smallSample'] is True
    assert data['consensus'][0] == {
        'choice': 'agree', 'statement': 'Shared maintenance matters',
        'percentage': 82,
    }
    assert data['groups'][0]['label'] == 'Group 1'
    serialized = json.dumps(data)
    assert conversation.polis_id not in serialized
    assert 'private-upstream-id' not in serialized


def test_intermediate_results_api_projects_recomputing_state(client, conversation):
    conversation.phase_public_results = True
    db.session.commit()
    with patch(
        'app._load_intermediate_results', return_value=(None, None, True),
    ):
        data = client.get(
            '/api/v1/conversations/test-conv/intermediate-results',
        ).get_json()['data']

    assert data['state'] == 'recomputing'
    assert data['consensus'] == []
    assert data['groups'] == []


def test_intermediate_results_api_rejects_unpublished_state(client, conversation):
    response = client.get(
        '/api/v1/conversations/test-conv/intermediate-results',
    )
    assert response.status_code == 409


def test_openapi_documents_intermediate_results(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths'][
        '/conversations/{slug}/intermediate-results'
    ]['get']
    assert operation['operationId'] == 'getIntermediateResults'
    assert operation['responses']['200']['content']['application/json'][
        'schema'
    ]['$ref'].endswith('/IntermediateResultsResponse')
