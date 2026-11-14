"""The report's Process timeline, replayed from the phase audit rows (#599)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app import PHASE_ROUTES, PHASE_SEQUENCE, _PHASE_BY_KEY
from db import AuditEvent, db
from services.phase_timeline import build_phase_timeline

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
FLAGS = [stage['flag'] for stage in PHASE_SEQUENCE if stage['flag']]


def _at(days):
    return T0 + timedelta(days=days)


def _iso(days):
    return _at(days).isoformat().replace('+00:00', 'Z')


def _conv(*, on=(), active=True, closed_at=None):
    flags = {flag: False for flag in FLAGS}
    flags.update({_PHASE_BY_KEY[key]['flag']: True for key in on})
    return SimpleNamespace(active=active, closed_at=closed_at, **flags)


def _route(name='default_7'):
    return [_PHASE_BY_KEY[key] for key in PHASE_ROUTES[name]['keys']]


def _advance(days, source, target, operation='phase.advance'):
    return (_at(days), operation, target, {'from_phase': source})


def _by_key(rows):
    return {row['key']: row for row in rows}


def test_guided_moves_give_each_phase_its_start_and_end():
    events = [
        _advance(0, 'preparation', 'submission'),
        _advance(10, 'submission', 'featured_selection'),
        _advance(12, 'featured_selection', 'argument_mapping', 'phase.schedule.fire'),
    ]
    rows = build_phase_timeline(
        conversation=_conv(on=['argument_mapping']), route=_route(), events=events,
    )

    assert [row['key'] for row in rows] == [
        'submission', 'featured_selection', 'argument_mapping',
        'cleanup', 'informed_voting', 'public_results',
    ]
    phases = _by_key(rows)
    assert phases['submission'] == {
        'key': 'submission', 'state': 'ended', 'startedAt': _iso(0), 'endedAt': _iso(10),
    }
    assert phases['featured_selection']['endedAt'] == _iso(12)
    assert phases['argument_mapping'] == {
        'key': 'argument_mapping', 'state': 'running',
        'startedAt': _iso(12), 'endedAt': None,
    }
    for key in ('cleanup', 'informed_voting', 'public_results'):
        assert phases[key] == {
            'key': key, 'state': 'not_started', 'startedAt': None, 'endedAt': None,
        }


def test_phases_the_route_skips_are_left_out():
    rows = build_phase_timeline(
        conversation=_conv(on=['submission']), route=_route('short_results'), events=[],
    )

    assert [row['key'] for row in rows] == [
        'submission', 'featured_selection', 'public_results',
    ]


def test_advanced_set_archive_reopen_and_close():
    events = [
        (_at(0), 'phase.set', None, {'active_keys': ['submission']}),
        (_at(3), 'conversation.archive', None, {}),
        (_at(4), 'conversation.reopen', None, {}),
        (_at(5), 'phase.set', None, {'active_keys': ['public_results']}),
        (_at(9), 'conversation.close', None, {'excluded_tids': 0, 'excluded_pids': 0}),
    ]
    rows = build_phase_timeline(
        conversation=_conv(on=['public_results'], active=False, closed_at=_at(9)),
        route=_route('short_results'), events=events,
    )

    phases = _by_key(rows)
    # Reopening resumes the phase: its first start stays, the archive's end goes.
    assert phases['submission'] == {
        'key': 'submission', 'state': 'ended', 'startedAt': _iso(0), 'endedAt': _iso(5),
    }
    assert phases['public_results'] == {
        'key': 'public_results', 'state': 'ended', 'startedAt': _iso(5), 'endedAt': _iso(9),
    }
    # Reached (it lies before the current phase) but never recorded: ended, dates unknown.
    assert phases['featured_selection'] == {
        'key': 'featured_selection', 'state': 'ended', 'startedAt': None, 'endedAt': None,
    }


def test_an_archived_phase_is_not_running():
    rows = build_phase_timeline(
        conversation=_conv(on=['submission'], active=False),
        route=_route('short_results'),
        events=[_advance(0, 'preparation', 'submission'),
                (_at(2), 'conversation.archive', None, {})],
    )

    assert _by_key(rows)['submission'] == {
        'key': 'submission', 'state': 'ended', 'startedAt': _iso(0), 'endedAt': _iso(2),
    }


def test_results_report_carries_phase_dates_from_the_audit_log(
    client, conversation, participant,
):
    conversation.phase_route = 'short_results'
    conversation.phase_public_results = True
    db.session.add_all([
        AuditEvent(ts=_at(0), actor_participant_id=participant.id,
                   conversation_id=conversation.id, operation='phase.advance',
                   target_type='phase', target_id='submission',
                   detail={'from_phase': 'preparation', 'phase6_created': False}),
        AuditEvent(ts=_at(7), actor_participant_id=participant.id,
                   conversation_id=conversation.id, operation='phase.advance',
                   target_type='phase', target_id='featured_selection',
                   detail={'from_phase': 'submission', 'phase6_created': False}),
        # A refused move changed nothing, so it is not a phase change.
        AuditEvent(ts=_at(8), actor_participant_id=participant.id,
                   conversation_id=conversation.id, operation='phase.advance',
                   target_type='phase', target_id='public_results', outcome='error',
                   detail={'from_phase': 'featured_selection'}),
        AuditEvent(ts=_at(9), actor_participant_id=participant.id,
                   conversation_id=conversation.id, operation='phase.advance',
                   target_type='phase', target_id='public_results',
                   detail={'from_phase': 'featured_selection', 'phase6_created': False}),
    ])
    db.session.commit()

    with patch('app._build_phase6_results', return_value=None):
        response = client.get('/api/v1/conversations/test-conv/results')

    assert response.status_code == 200
    phases = response.get_json()['data']['phases']
    assert phases == [
        {'key': 'submission', 'state': 'ended', 'startedAt': _iso(0), 'endedAt': _iso(7)},
        {'key': 'featured_selection', 'state': 'ended',
         'startedAt': _iso(7), 'endedAt': _iso(9)},
        {'key': 'public_results', 'state': 'running', 'startedAt': _iso(9), 'endedAt': None},
    ]  # Keys and dates only (exact equality): nothing about who made the change.


def test_openapi_documents_the_report_phases(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    report = spec['components']['schemas']['ResultsReport']
    phase = spec['components']['schemas']['ResultsReportPhase']

    assert 'phases' in report['required']
    assert set(phase['required']) == {'key', 'state', 'startedAt', 'endedAt'}
    assert phase['additionalProperties'] is False
