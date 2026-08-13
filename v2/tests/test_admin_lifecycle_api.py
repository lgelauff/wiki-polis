"""Admin lifecycle read-contract tests."""

from datetime import datetime, timedelta, timezone

from db import AdminRole, AuditEvent, FeaturedStatement, db
from tests.conftest import login
from services.admin_lifecycle import PhaseTransitionSaveFailed
from unittest.mock import patch


def test_lifecycle_contract_separates_phase_from_publication(
    admin_client, conversation,
):
    conversation.phase_public_results = True
    conversation.phase6_polis_conversation_id = 'p6-private'
    db.session.commit()

    pending = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).get_json()['data']

    assert pending['conversation']['publication'] == 'pending'
    assert pending['phase']['steps'][-1]['state'] == 'current'
    assert pending['capabilities']['publish'] is True
    assert pending['publicationReadiness']['windowOpen'] is True
    assert pending['publicationReadiness']['preconditions'][-1]['met'] is True
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
    publication = response.get_json()['data']['publicationReadiness']
    assert publication['windowOpen'] is False
    assert publication['preconditions'][-1] == {
        'id': 'phase6_initialized',
        'label': 'Informed voting round initialized',
        'met': False,
        'note': 'Initialize informed voting before publishing.',
    }
    controls = response.get_json()['data']['phase']['advancedControls']
    assert controls[0]['key'] == 'submission'
    assert all('phase_' not in row['key'] for row in controls)
    informed = next(row for row in controls if row['key'] == 'informed_voting')
    assert informed['requiresInitialization'] is True
    assert informed['initialized'] is False


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
        'archive': False,
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


def test_pause_api_is_desired_state_and_idempotent(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/pause'
    first = admin_client.put(endpoint, json={'paused': True})
    replay = admin_client.put(endpoint, json={'paused': True})
    resumed = admin_client.put(endpoint, json={'paused': False})

    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    assert resumed.get_json()['data']['lifecycle']['conversation']['status'] == 'active'
    assert [event.operation for event in AuditEvent.query.order_by(AuditEvent.id)] == [
        'conversation.pause', 'conversation.pause',
    ]


def test_publication_api_enforces_cleanup_and_readiness(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/publication'
    early = admin_client.post(endpoint, json={'confirmedPreconditionIds': []})
    conversation.phase_public_results = True
    conversation.phase6_polis_conversation_id = 'p6-private'
    db.session.commit()
    incomplete = admin_client.post(endpoint, json={'confirmedPreconditionIds': []})

    assert early.status_code == 409
    assert early.get_json()['error']['code'] == 'publication_unavailable'
    assert incomplete.status_code == 409
    assert incomplete.get_json()['error']['code'] == 'readiness_unconfirmed'


def test_publication_api_freezes_report_and_returns_published_lifecycle(
    admin_client, conversation,
):
    conversation.phase_public_results = True
    conversation.phase6_polis_conversation_id = 'p6-private'
    db.session.commit()
    confirmed = [
        'cleanup_reviewed_results', 'cleanup_moderated_flagged',
        'cleanup_reviewed_exclusions', 'cleanup_report_intro',
    ]
    with patch('app.PolisServerClient.get_statements', return_value=([], [], [])):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/publication',
            json={'confirmedPreconditionIds': confirmed},
        )

    assert response.status_code == 201
    lifecycle = response.get_json()['data']['lifecycle']
    assert lifecycle['conversation']['publication'] == 'published'
    assert lifecycle['conversation']['status'] == 'closed'
    assert 'p6-private' not in response.text


def test_schedule_api_converges_and_cancels(admin_client, conversation):
    conversation.phase_submission = True
    db.session.commit()
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/schedule'
    scheduled_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    body = {'scheduledAt': scheduled_at.isoformat(), 'frozen': False}

    first = admin_client.put(endpoint, json=body)
    replay = admin_client.put(endpoint, json=body)
    cancel = admin_client.put(
        endpoint, json={'scheduledAt': None, 'frozen': False},
    )
    cancel_replay = admin_client.put(
        endpoint, json={'scheduledAt': None, 'frozen': False},
    )

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    assert first.get_json()['data']['lifecycle']['schedule']['targetKey'] == 'featured_selection'
    assert cancel.get_json()['data']['changed'] is True
    assert cancel_replay.get_json()['data']['changed'] is False
    assert cancel.get_json()['data']['lifecycle']['schedule']['scheduledAt'] is None


def test_schedule_api_rejects_unschedulable_and_past_transitions(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/schedule'
    future = datetime.now(timezone.utc) + timedelta(days=1)
    unavailable = admin_client.put(
        endpoint, json={'scheduledAt': future.isoformat(), 'frozen': False},
    )
    past = admin_client.put(
        endpoint,
        json={'scheduledAt': '2020-01-01T00:00:00Z', 'frozen': False},
    )

    assert unavailable.status_code == 409
    assert unavailable.get_json()['error']['code'] == 'schedule_unavailable'
    assert past.status_code == 400
    assert past.get_json()['error']['code'] == 'schedule_time_invalid'


def test_advanced_phase_api_replaces_route_keys_and_is_idempotent(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/phases'
    body = {'activeKeys': ['argument_mapping', 'cleanup']}

    first = admin_client.put(endpoint, json=body)
    replay = admin_client.put(endpoint, json=body)

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    assert first.get_json()['data']['activeKeys'] == ['argument_mapping', 'cleanup']
    db.session.refresh(conversation)
    assert conversation.phase_argument_mapping is True
    assert conversation.phase_cleanup is True
    assert conversation.phase_submission is False


def test_advanced_phase_api_rejects_key_outside_locked_route(
    admin_client, conversation,
):
    conversation.phase_route = 'short_results'
    db.session.commit()

    response = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/phases',
        json={'activeKeys': ['argument_mapping']},
    )

    assert response.status_code == 400
    assert response.get_json()['error'] == {
        'code': 'phase_not_in_route',
        'message': 'One or more phases are not part of this conversation route.',
        'details': {'phaseKeys': ['argument_mapping']},
    }


def test_archive_api_is_reversible_without_publication_side_effects(
    admin_client, conversation,
):
    conversation.paused = True
    conversation.phase_public_results = True
    conversation.scheduled_transition_at = datetime.now(timezone.utc) + timedelta(days=1)
    conversation.scheduled_transition_target = 'closed'
    db.session.commit()
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/archive'

    archived = admin_client.put(endpoint, json={'archived': True})
    replay = admin_client.put(endpoint, json={'archived': True})
    reopened = admin_client.put(endpoint, json={'archived': False})

    assert archived.status_code == replay.status_code == reopened.status_code == 200
    assert archived.get_json()['data']['lifecycle']['conversation'] == {
        'id': conversation.id,
        'slug': conversation.slug,
        'title': conversation.title,
        'accessPolicy': conversation.access_policy,
        'status': 'archived',
        'publication': 'not_applicable',
        'closedAt': None,
    }
    assert archived.get_json()['data']['changed'] is True
    assert archived.get_json()['data']['lifecycle']['capabilities']['advancePhase'] is False
    assert archived.get_json()['data']['lifecycle']['schedule']['canSchedule'] is False
    assert replay.get_json()['data']['changed'] is False
    assert reopened.get_json()['data']['lifecycle']['conversation']['status'] == 'active'
    db.session.refresh(conversation)
    assert conversation.active is True
    assert conversation.paused is False
    assert conversation.phase_public_results is False
    assert conversation.closed_at is None
    assert conversation.report_filter_snapshot is None
    assert conversation.scheduled_transition_at is None
    assert AuditEvent.query.filter(
        AuditEvent.operation.in_(['conversation.archive', 'conversation.reopen']),
    ).count() == 2


def test_archive_api_refuses_published_conversation(admin_client, conversation):
    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc)
    db.session.commit()

    response = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/archive',
        json={'archived': True},
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'conversation_closed'
