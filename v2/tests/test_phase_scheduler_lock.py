"""An overlapping scheduler run must not fire (or abort) the same transition twice.

SQLite has no row locks, so two truly concurrent runs cannot be staged here, and the "overlap"
tests below run the per-conversation step twice in a row: they prove the re-check after locking,
not that the second run waits. The lock itself is guarded only by the first test, which checks
that each due conversation is taken with a plain ``SELECT … FOR UPDATE`` (every MariaDB version,
unlike SKIP LOCKED). Two real concurrent runs need two connections against MariaDB.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sqlalchemy.orm
from sqlalchemy.dialects import mysql

import app as app_module
from db import AuditEvent, db


def _due(conversation, target='featured_selection'):
    conversation.phase_submission = True
    conversation.scheduled_transition_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    conversation.scheduled_transition_target = target
    db.session.commit()


def _audit(operation):
    return AuditEvent.query.filter_by(operation=operation).count()


def test_each_due_conversation_is_locked_with_a_plain_for_update(app, conversation):
    _due(conversation)
    calls = []
    original = sqlalchemy.orm.Query.with_for_update

    def spy(self, *args, **kwargs):
        calls.append(kwargs)
        query = original(self, *args, **kwargs)
        calls[-1]['sql'] = str(query.statement.compile(dialect=mysql.dialect()))
        return query

    with patch.object(sqlalchemy.orm.Query, 'with_for_update', spy), \
            patch('app.PolisServerClient.set_vis_type', return_value=True):
        result = app_module._process_due_scheduled_transitions()

    assert result == {'fired': 1, 'aborted': 0, 'skipped': 0, 'failed': 0}
    assert len(calls) == 1                                    # one lock per conversation, none on the list
    assert not calls[0].get('skip_locked')
    assert 'FOR UPDATE' in calls[0]['sql'] and 'SKIP LOCKED' not in calls[0]['sql']


def test_an_overlapping_run_does_not_fire_the_same_transition_twice(app, conversation):
    _due(conversation)
    now = datetime.now(timezone.utc)
    with patch('app.PolisServerClient.set_vis_type', return_value=True):
        # Both runs read the candidate list before either acted; then each takes the lock in turn.
        first = app_module._process_one_scheduled_transition(conversation.id, now)
        second = app_module._process_one_scheduled_transition(conversation.id, now)

    assert (first, second) == ('fired', 'skipped')
    assert _audit('phase.schedule.fire') == 1


def test_an_overlapping_run_does_not_abort_the_same_schedule_twice(app, conversation):
    _due(conversation, target='informed_voting')              # not the next phase: blocked
    now = datetime.now(timezone.utc)
    first = app_module._process_one_scheduled_transition(conversation.id, now)
    second = app_module._process_one_scheduled_transition(conversation.id, now)

    assert (first, second) == ('aborted', 'skipped')
    assert _audit('phase.schedule.abort') == 1
    db.session.refresh(conversation)
    assert conversation.scheduled_transition_frozen is True


def test_a_schedule_not_yet_due_is_skipped_and_left_alone(app, conversation):
    _due(conversation)
    conversation.scheduled_transition_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.session.commit()

    result = app_module._process_due_scheduled_transitions()

    assert result == {'fired': 0, 'aborted': 0, 'skipped': 1, 'failed': 0}
    db.session.refresh(conversation)
    assert conversation.scheduled_transition_at is not None and conversation.phase_submission is True


def test_one_failing_conversation_does_not_block_the_others(app, conversation):
    _due(conversation)
    other = type(conversation)(slug='other-conv', polis_id='def7654321', title='Other',
                               active=True, access_policy='public')
    db.session.add(other)
    db.session.commit()
    _due(other)
    real = app_module._process_one_scheduled_transition

    def flaky(conv_id, now):
        if conv_id == conversation.id:
            raise RuntimeError('boom')
        return real(conv_id, now)

    with patch('app._process_one_scheduled_transition', side_effect=flaky), \
            patch('app.PolisServerClient.set_vis_type', return_value=True):
        result = app_module._process_due_scheduled_transitions()

    assert result == {'fired': 1, 'aborted': 0, 'skipped': 0, 'failed': 1}
    db.session.refresh(other)
    assert other.scheduled_transition_at is None                 # the other one still fired

