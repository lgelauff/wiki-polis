"""Admin lifecycle read-contract tests."""

from datetime import datetime, timezone

from db import AdminRole, FeaturedStatement, db
from tests.conftest import login


def test_lifecycle_contract_separates_phase_from_publication(
    admin_client, conversation,
):
    conversation.phase_public_results = True
    db.session.commit()

    pending = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']

    assert pending['conversation']['publication'] == 'pending'
    assert pending['phase']['steps'][-1]['state'] == 'current'
    assert pending['capabilities']['publish'] is True
    assert pending['phase']['transition'] is None
    assert pending['links']['participants'].endswith(
        f'/app/admin/conversations/{conversation.id}/participants'
    )

    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    published = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']
    assert published['conversation']['publication'] == 'published'
    assert published['capabilities']['publish'] is False


def test_lifecycle_contract_exposes_server_evaluated_transition(
    admin_client, conversation,
):
    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    )

    assert response.status_code == 200
    transition = response.get_json()['data']['phase']['transition']
    assert transition['source'] == {'key': 'preparation', 'label': 'Preparation'}
    assert transition['target'] == {'key': 'submission', 'label': 'Explore'}
    assert len(transition['preconditions']) == 6
    assert all({'id', 'label', 'met', 'note'} == set(row) for row in transition['preconditions'])


def test_scoped_moderator_lifecycle_capabilities_are_read_only(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')

    data = client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']

    assert data['operator']['roleLabel'] == 'Moderator'
    assert data['capabilities'] == {
        'advancePhase': False,
        'pause': False,
        'publish': False,
        'editSettings': False,
        'useAdvancedPhases': False,
    }


def test_lifecycle_contract_omits_upstream_identifiers(
    admin_client, conversation,
):
    conversation.phase6_polis_conversation_id = 'private-round-six'
    db.session.add(FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=42,
        phase6_polis_statement_id=84,
        statement_text='Featured',
        confirmed_by_admin=True,
    ))
    db.session.commit()

    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    )

    assert conversation.polis_id not in response.text
    assert 'private-round-six' not in response.text


def test_lifecycle_contract_requires_moderation_access(
    auth_client, conversation,
):
    assert auth_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).status_code == 403


def test_openapi_documents_admin_lifecycle(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/admin/conversations/{conversationId}']['get']
    publication = spec['components']['schemas']['AdminLifecycleConversation']['properties']['publication']
    assert operation['operationId'] == 'getAdminConversationLifecycle'
    assert publication['enum'] == ['not_applicable', 'pending', 'published']
