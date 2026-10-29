"""Site-admin report preview: any phase, never published, audited."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import app as app_module
from app import Phase6ResultsFilter
from db import AdminRole, AuditEvent, Participant, db
from tests.conftest import login
from tests.test_results_report_api import _results


def _url(conversation):
    return f'/api/v1/admin/conversations/{conversation.id}/report-preview'


def _state(conversation):
    return (
        conversation.closed_at, conversation.active, conversation.paused,
        conversation.phase_public_results, conversation.phase_personal_results,
        conversation.report_filter_snapshot,
    )


def _no_publication():
    """Fail the test if the preview tries to publish or snapshot anything."""
    def refuse(*_args, **_kwargs):
        raise AssertionError('a preview must not publish or snapshot')
    return (
        patch('app._publish_final_report', side_effect=refuse),
        patch('app._snapshot_report_filter', side_effect=refuse),
    )


def test_preview_works_before_results_are_published(admin_client, conversation):
    """The public endpoint refuses here (409); the preview does not."""
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()
    before = _state(conversation)
    seen = {}

    def build(_conversation, participation, results_filter=None):
        seen['participation'] = participation
        seen['filter'] = results_filter
        return _results()

    publish, snapshot = _no_publication()
    live = Phase6ResultsFilter(excluded_tids=frozenset({3}), excluded_pids=frozenset())
    with patch('app._build_phase6_results', side_effect=build), \
            patch('app._current_phase6_results_filter', return_value=live), \
            publish, snapshot:
        public = admin_client.get('/api/v1/conversations/test-conv/results')
        response = admin_client.get(_url(conversation))

    assert public.status_code == 409
    assert response.status_code == 200
    assert response.headers['Cache-Control'].startswith('no-store')
    data = response.get_json()['data']
    assert data['publication'] == 'preview'
    assert data['resultsAvailable'] is True
    assert data['viewer'] == {
        'participating': False, 'pseudonym': None, 'revealState': None,
    }
    assert data['links']['conversation'].endswith(f'/admin/conversations/{conversation.id}')
    assert 'identityReveal' not in data['links']
    assert seen == {'participation': None, 'filter': live}
    db.session.refresh(conversation)
    assert _state(conversation) == before
    serialized = json.dumps(data)
    assert conversation.polis_id not in serialized
    assert conversation.phase6_polis_conversation_id not in serialized


def test_preview_before_informed_voting_is_an_empty_report(admin_client, conversation):
    response = admin_client.get(_url(conversation))

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['publication'] == 'preview'
    assert data['resultsAvailable'] is False
    assert data['statements'] == []


def test_preview_of_a_closed_process_reads_the_snapshot(admin_client, conversation):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    conversation.report_filter_snapshot = {'excluded_tids': [42], 'excluded_pids': [7]}
    db.session.commit()
    seen = {}

    def build(_conversation, participation, results_filter=None):
        seen['filter'] = results_filter
        return _results()

    publish, snapshot = _no_publication()
    with patch('app._build_phase6_results', side_effect=build), \
            patch('app._current_phase6_results_filter',
                  side_effect=AssertionError('closed: snapshot only')), \
            publish, snapshot:
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['publication'] == 'preview'
    assert seen['filter'] == Phase6ResultsFilter(
        excluded_tids=frozenset({42}), excluded_pids=frozenset({7}),
    )
    db.session.refresh(conversation)
    assert conversation.report_filter_snapshot == {
        'excluded_tids': [42], 'excluded_pids': [7],
    }


def test_preview_skips_the_gate_of_a_private_process(admin_client, conversation):
    """Site admins have no exception in the access check, so the preview must not use it."""
    conversation.gated = True
    conversation.gating_type = 'invite_only'
    db.session.commit()

    public = admin_client.get('/api/v1/conversations/test-conv/results')
    assert public.status_code == 403
    assert public.get_json()['error']['code'] == 'access_required'
    assert admin_client.get(_url(conversation)).status_code == 200


def test_preview_is_for_site_admins_only(client, participant, conversation):
    assert client.get(_url(conversation)).status_code == 401

    db.session.add(AdminRole(
        participant_id=participant.id, conversation_id=conversation.id, role='organizer',
    ))
    db.session.commit()
    login(client, 'testuser')
    response = client.get(_url(conversation))

    assert response.status_code == 403
    assert AuditEvent.query.filter_by(operation='report.preview').count() == 0


def test_preview_unknown_conversation_is_404(admin_client):
    assert admin_client.get('/api/v1/admin/conversations/999/report-preview').status_code == 404


def test_preview_writes_one_privacy_safe_audit_event(
    admin_client, admin_participant, conversation,
):
    conversation.phase_informed_voting = True
    db.session.commit()

    admin_client.get(_url(conversation))

    events = AuditEvent.query.filter_by(operation='report.preview').all()
    assert len(events) == 1
    event = events[0]
    assert event.actor_participant_id == admin_participant.id
    assert event.conversation_id == conversation.id
    assert (event.target_type, event.target_id) == ('conversation', str(conversation.id))
    assert event.detail == {
        'phase': 'informed_voting', 'source': 'live', 'results_available': False,
    }
    stored = json.dumps(event.detail)
    assert 'adminuser' not in stored
    assert conversation.title not in stored


def test_config_listed_admin_without_a_participant_row_can_preview(
    client, conversation, monkeypatch,
):
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['Config-admin'])
    login(client, 'Config-admin')
    assert Participant.query.filter_by(mw_username='Config-admin').first() is None

    response = client.get(_url(conversation))

    assert response.status_code == 200
    event = AuditEvent.query.filter_by(operation='report.preview').one()
    assert event.actor_participant_id is None
    assert event.detail['actor_kind'] == 'env_admin'
    assert 'Config-admin' not in json.dumps(event.detail)


def test_lifecycle_offers_the_preview_to_site_admins_until_closed(
    admin_client, client, participant, conversation,
):
    url = f'/api/v1/admin/conversations/{conversation.id}'
    assert admin_client.get(url).get_json()['data']['capabilities']['previewReport'] is True

    conversation.active = False
    conversation.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    assert admin_client.get(url).get_json()['data']['capabilities']['previewReport'] is False


def test_openapi_documents_the_report_preview(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/admin/conversations/{conversationId}/report-preview']['get']
    report = spec['components']['schemas']['ResultsReport']

    assert operation['operationId'] == 'getAdminConversationReportPreview'
    assert 'preview' in report['properties']['publication']['enum']
    capabilities = spec['components']['schemas']['AdminLifecycle']['properties']['capabilities']
    assert 'previewReport' in capabilities['required']
