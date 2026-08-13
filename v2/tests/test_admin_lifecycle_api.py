"""Admin lifecycle read-contract tests."""

from datetime import datetime, timezone

from db import AdminRole, FeaturedStatement, db
from tests.conftest import login
from services.admin_lifecycle import PhaseTransitionSaveFailed
from unittest.mock import patch


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


def test_phase_advance_api_returns_receipt_and_refreshed_lifecycle(
    admin_client, conversation,
):
    before = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']
    ids = [row['id'] for row in before['phase']['transition']['preconditions']]

    with patch('app.PolisServerClient.set_vis_type', return_value=True):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/phase',
            json={'confirmedPreconditionIds': ids},
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['transition']['sourceKey'] == 'preparation'
    assert data['transition']['targetKey'] == 'submission'
    assert data['transition']['visibilitySynced'] is True
    assert data['lifecycle']['phase']['steps'][1]['state'] == 'current'


def test_phase_advance_api_reports_missing_and_machine_blocked_checks(
    admin_client, conversation,
):
    missing = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/phase',
        json={'confirmedPreconditionIds': []},
    )
    conversation.phase_personal_results = True
    db.session.commit()
    state = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']
    ids = [row['id'] for row in state['phase']['transition']['preconditions']]
    blocked = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/phase',
        json={'confirmedPreconditionIds': ids},
    )

    assert missing.status_code == 409
    assert missing.get_json()['error']['code'] == 'readiness_unconfirmed'
    assert blocked.status_code == 409
    assert blocked.get_json()['error']['code'] == 'readiness_blocked'


def test_phase_advance_api_marks_post_upstream_save_failure_unknown(
    admin_client, conversation,
):
    with patch(
        'app._advance_admin_phase_command',
        side_effect=PhaseTransitionSaveFailed(
            outcome_unknown=True, orphaned_phase6_id='private-id',
        ),
    ):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/phase',
            json={'confirmedPreconditionIds': ['ready']},
        )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'command_outcome_unknown'
    assert 'private-id' not in response.text


def test_phase_advance_api_requires_organizer(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')

    response = client.put(
        f'/api/v1/admin/conversations/{conversation.id}/phase',
        json={'confirmedPreconditionIds': []},
    )
    assert response.status_code == 403
