"""Conversation workspace composition contract tests."""

import json
from datetime import datetime, timedelta, timezone

from db import Participation, db


def _join(participant, conversation, pseudonym='workspace-otter'):
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym=pseudonym,
    )
    db.session.add(participation)
    db.session.commit()
    return participation


def test_workspace_contract_owns_legacy_tab_composition(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    conversation.intro_text = '<p>A <strong>shared</strong> question.</p>'
    conversation.phase_submission = True
    conversation.phase_personal_results = True
    conversation.phase_argument_mapping = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'phase6abc123'
    conversation.argument_vote_data = {
        'new_stmt_unlock_at': 7,
        'new_stmt_max': 4,
    }
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/workspace')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['status'] == 'open'
    assert data['descriptionHtml'] == '<p>A <strong>shared</strong> question.</p>'
    assert data['viewer'] == {
        'state': 'participant', 'pseudonym': 'workspace-otter',
    }
    assert data['spaceWarning'] == 'real'
    assert data['defaultTab'] == 'vote'
    assert [(tab['key'], tab['label']) for tab in data['tabs']] == [
        ('vote', 'Vote'),
        ('results', 'Intermediate results'),
        ('arguments', 'Arguments'),
        ('informed-voting', 'Informed vote'),
    ]
    assert data['tabs'][0]['dataHref'] == (
        '/api/v1/conversations/test-conv/explore'
    )
    assert data['tabs'][1]['dataHref'] is None
    assert data['statementContribution'] == {
        'unlockAfter': 7, 'quota': 4, 'used': 0,
    }
    assert data['capabilities'] == {'participate': True, 'moderate': False}
    assert data['links']['join'] == '/app/conversations/test-conv/join'
    assert data['links']['informedVoting'] == (
        '/api/v1/conversations/test-conv/informed-voting'
    )
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert conversation.polis_id not in serialized

    repeated = auth_client.get('/api/v1/conversations/test-conv/workspace')
    assert repeated.get_json()['data']['spaceWarning'] is None


def test_workspace_returns_join_required_without_exposing_phase_data(
    auth_client, conversation,
):
    conversation.phase_submission = True
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/workspace')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['viewer'] == {'state': 'join_required', 'pseudonym': None}
    assert data['spaceWarning'] is None
    assert data['capabilities']['participate'] is False


def test_workspace_closed_state_projects_reveal_timeline(
    auth_client, participant, conversation,
):
    participation = _join(participant, conversation, 'closed-otter')
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/workspace')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['status'] == 'closed'
    assert data['tabs'] == []
    assert data['defaultTab'] is None
    assert data['reveal']['state'] == 'open'
    assert data['reveal']['pseudonym'] == participation.pseudonym
    assert data['reveal']['closedAt'].endswith('Z')
    assert data['capabilities']['participate'] is False


def test_workspace_requires_real_authentication(client, conversation):
    response = client.get('/api/v1/conversations/test-conv/workspace')

    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'unauthorized'


def test_openapi_describes_conversation_workspace(client):
    spec = client.get('/api/v1/openapi.json').get_json()

    operation = spec['paths']['/conversations/{slug}/workspace']['get']
    assert operation['operationId'] == 'getConversationWorkspace'
    assert (
        operation['responses']['200']['content']['application/json']['schema']['$ref']
        == '#/components/schemas/ConversationWorkspaceResponse'
    )
