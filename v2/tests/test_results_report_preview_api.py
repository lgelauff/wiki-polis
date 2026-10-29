"""Site-admin report preview: any phase, never published, audited."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from flask import g

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


def test_preview_of_a_published_report_points_to_it(admin_client, conversation):
    """Nothing to preview once published: 409 with the published report's path, no audit row."""
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    db.session.commit()

    publish, snapshot = _no_publication()
    with patch('app._build_phase6_results',
               side_effect=AssertionError('published: nothing to build')), publish, snapshot:
        response = admin_client.get(_url(conversation))

    assert response.status_code == 409
    error = response.get_json()['error']
    assert error['code'] == 'conversation_closed'
    assert error['details'] == {'report': '/c/test-conv/report'}
    assert AuditEvent.query.filter_by(operation='report.preview').count() == 0


def test_preview_rows_are_sorted_by_shift_like_the_report(admin_client, conversation):
    """The builder orders an open process's rows by id; the preview orders them as the report."""
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()
    base = _results()
    row = base['statements'][0]
    base['statements'] = [
        {**row, 'fs_id': 1, 'shift': 2.0},
        {**row, 'fs_id': 2, 'shift': -15.0},
        {**row, 'fs_id': 3, 'shift': None},
        {**row, 'fs_id': 4, 'shift': 8.0},
    ]

    with patch('app._build_phase6_results', return_value=base):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert [s['featuredStatementId'] for s in data['statements']] == [2, 4, 1, 3]


def test_preview_is_read_as_the_report_but_not_final(admin_client, conversation):
    conversation.phase_informed_voting = True
    db.session.commit()

    data = admin_client.get(_url(conversation)).get_json()['data']

    report = next(
        item for item in app_module._output_items(conversation) if item['key'] == 'report'
    )
    assert data['context']['phase'] == report['phase']
    assert data['context']['method'] == report['method']
    assert data['context']['status'] == 'provisional'


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


def test_preview_unknown_conversation_is_404_only_for_site_admins(
    app, admin_client, participant,
):
    """The site-admin check comes first, so nobody else learns which ids exist."""
    url = '/api/v1/admin/conversations/999/report-preview'
    other = app.test_client()
    login(other, 'testuser')
    assert other.get(url).status_code == 403
    # The fixture's app context outlives a request, so drop the participant it cached.
    g.pop('participant', None)
    assert admin_client.get(url).status_code == 404


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
    assert event.detail == {'phase': 'informed_voting', 'results_available': False}
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


def test_preview_has_the_full_report_shape_while_informed_voting_is_open(
    admin_client, conversation,
):
    """The public endpoint shows nothing in this phase; the preview shows the whole report."""
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()

    with patch('app._build_phase6_results', return_value=_results()):
        public = admin_client.get('/api/v1/conversations/test-conv/results')
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert public.status_code == 409
    assert data['publication'] == 'preview'
    assert data['statements'][0]['initial'] is not None
    assert data['statements'][0]['agreementShift'] == 10.0
    assert data['participation']['initialRound'] == 25
    assert data['dataAvailability']['opinionGroups'] is True
    assert len(data['opinionGroups']) == 1
    assert data['dataAvailability']['personalLens'] is False
