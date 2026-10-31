"""The daily reminder batch, in dry-run (#577)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from db import Conversation, Participant, Participation, Reminder, ReminderDelivery, db
from services.reminder_batch import (
    DryRunSender, Outcome, ReminderNotFound, run_batch, unlink_ended,
)
from services.reminders import PHASE_OPENED, RESULTS
from tests.conftest import _xid

DAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 6, 0)
APPROVED = {'metawiki': '#582', 'nlwiki': '#581'}


class Recording:
    """A sender that records each call and answers from a script."""

    def __init__(self, answer=None):
        self.calls = []
        self._answer = answer or (lambda **kw: Outcome('dry_run', sent_via=kw['wiki']))

    def send(self, **kw):
        self.calls.append(kw)
        return self._answer(**kw)


_ids = iter(range(5000, 9000))


def _conversation(wiki='metawiki', **fields):
    n = next(_ids)
    fields = {'active': True, **fields}
    conv = Conversation(slug=f'c{n}', polis_id=f'p{n}', title=f'C{n}', reminder_wiki=wiki,
                        **fields)
    db.session.add(conv)
    db.session.commit()
    return conv


def _person():
    n = next(_ids)
    person = Participant(mw_user_id=n, mw_username=f'User{n}', xid=_xid(n))
    db.session.add(person)
    db.session.commit()
    return person


def _join(conv, person, *, email=True, talk=False):
    joined = Participation(participant_id=person.id, conversation_id=conv.id,
                           pseudonym=f'p{next(_ids)}', notify_email=email, notify_talk_page=talk)
    db.session.add(joined)
    db.session.commit()
    return joined


def _remind(conv, *, kind=PHASE_OPENED, phase='submission', day=DAY):
    reminder = Reminder(conversation_id=conv.id, reminder_type=kind, phase_key=phase,
                        send_day=day)
    db.session.add(reminder)
    db.session.commit()
    return reminder


def _run(sender=None, *, cap=20, approved=APPROVED, phases=None, **kw):
    phases = phases or (lambda conv: {'submission'})
    return run_batch(DAY, now=NOW, active_phases=phases, sender=sender or Recording(),
                     email_cap=cap, approved=approved, **kw)


def _statuses(reminder):
    return sorted((row.channel, row.status) for row in
                  ReminderDelivery.query.filter_by(reminder_id=reminder.id))


def test_a_dry_run_records_every_recipient_and_calls_no_wiki(app):
    conv = _conversation()
    _join(conv, _person(), email=True, talk=True)
    _join(conv, _person(), email=True)
    reminder = _remind(conv)
    result = run_batch(DAY, now=NOW, active_phases=lambda c: {'submission'},
                       sender=DryRunSender(), email_cap=20, approved=APPROVED)
    assert _statuses(reminder) == [('email', 'dry_run'), ('email', 'dry_run'), ('talk', 'dry_run')]
    assert result.counts[('email', 'dry_run')] == 2
    assert {row.sent_via for row in ReminderDelivery.query} == {'metawiki'}


def test_paused_handles_nothing(app):
    conv = _conversation()
    _join(conv, _person())
    _remind(conv)
    sender = Recording()
    result = _run(sender, paused=True)
    assert result.paused and sender.calls == [] and ReminderDelivery.query.count() == 0


def test_the_scheduled_run_waits_on_a_wiki_where_the_bot_is_not_approved(app):
    conv = _conversation(wiki='nlwiki')
    _join(conv, _person())
    _remind(conv)
    sender = Recording()
    result = _run(sender, approved={'metawiki': '#582'})
    assert result.waiting_for_trigger == 1 and result.reminders == 0
    assert sender.calls == [] and ReminderDelivery.query.count() == 0


def test_a_super_admin_trigger_sends_on_a_wiki_that_is_not_approved(app):
    conv = _conversation(wiki='nlwiki')
    _join(conv, _person())
    reminder = _remind(conv)
    sender = Recording()
    _run(sender, approved={}, reminder_id=reminder.id)
    assert [call['wiki'] for call in sender.calls] == ['nlwiki']
    assert _statuses(reminder) == [('email', 'dry_run')]


def test_an_unknown_reminder_is_refused(app):
    with pytest.raises(ReminderNotFound):
        _run(reminder_id=999)


def test_one_message_per_person_per_day_and_channel_across_consultations(app):
    person = _person()
    first, second = _conversation(), _conversation()
    _join(first, person)
    _join(second, person)
    one, two = _remind(first), _remind(second)
    sender = Recording()
    _run(sender)
    assert len(sender.calls) == 1
    assert [r.id for r in sender.calls[0]['reminders']] == [one.id, two.id]
    assert _statuses(one) == [('email', 'dry_run')]
    assert _statuses(two) == [('email', 'combined')]


def test_talk_notes_combine_per_wiki_since_each_wiki_has_its_own_talk_page(app):
    person = _person()
    meta, nl = _conversation('metawiki'), _conversation('nlwiki')
    _join(meta, person, email=False, talk=True)
    _join(nl, person, email=False, talk=True)
    _remind(meta)
    _remind(nl)
    sender = Recording()
    _run(sender)
    assert sorted(call['wiki'] for call in sender.calls) == ['metawiki', 'nlwiki']


def test_the_wiki_mail_cap_goes_least_recently_mailed_first(app):
    conv = _conversation()
    mailed_before, never_a, never_b = _person(), _person(), _person()
    earlier = _remind(_conversation(), day=DAY - timedelta(days=3))
    old_join = _join(earlier.conversation, mailed_before)
    db.session.add(ReminderDelivery(reminder_id=earlier.id, participation_id=old_join.id,
                                    channel='email', status='sent',
                                    attempted_at=NOW - timedelta(days=3)))
    db.session.commit()
    for person in (mailed_before, never_a, never_b):
        _join(conv, person)
    reminder = _remind(conv)
    sender = Recording()
    _run(sender, cap=2)
    held = ReminderDelivery.query.filter_by(reminder_id=reminder.id, status='not_sent_limit').one()
    assert held.participation.participant_id == mailed_before.id
    assert len(sender.calls) == 2


def test_the_cap_counts_mail_already_sent_today(app):
    conv = _conversation()
    for _ in range(3):
        _join(conv, _person())
    first = _remind(conv)
    _run(cap=2)
    assert _statuses(first).count(('email', 'not_sent_limit')) == 1
    later = _remind(conv)
    sender = Recording()
    _run(sender, cap=2, reminder_id=later.id)
    assert sender.calls == []
    assert _statuses(later) == [('email', 'not_sent_limit')] * 3


def test_an_expired_reminder_is_recorded_and_not_sent(app):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv)
    sender = Recording()
    _run(sender, phases=lambda c: {'featured_selection'})
    assert sender.calls == [] and _statuses(reminder) == [('email', 'skipped_expired')]


def test_the_final_message_goes_out_once_the_consultation_closed(app):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv, kind=RESULTS, phase=None)
    _run(phases=lambda c: {'public_results', 'closed'})
    assert _statuses(reminder) == [('email', 'dry_run')]


def test_running_twice_handles_nothing_twice(app):
    conv = _conversation()
    _join(conv, _person(), talk=True)
    reminder = _remind(conv)
    first, second = Recording(), Recording()
    _run(first)
    _run(second)
    assert len(first.calls) == 2 and second.calls == []
    assert ReminderDelivery.query.filter_by(reminder_id=reminder.id).count() == 2


def test_a_row_claimed_by_another_run_is_left_alone(app):
    conv = _conversation()
    joined = _join(conv, _person())
    reminder = _remind(conv)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email', claimed_at=NOW))
    db.session.commit()
    sender = Recording()
    _run(sender)
    assert sender.calls == [] and _statuses(reminder) == [('email', 'pending')]


def test_a_failure_is_recorded_with_its_reason_and_not_moved_to_the_other_channel(app):
    conv = _conversation()
    _join(conv, _person(), email=True, talk=False)
    reminder = _remind(conv)
    sender = Recording(lambda **kw: Outcome('failed', reason='not_emailable'))
    _run(sender)
    assert len(sender.calls) == 1
    row = ReminderDelivery.query.filter_by(reminder_id=reminder.id).one()
    assert (row.channel, row.status, row.reason) == ('email', 'failed', 'not_emailable')


def test_a_blocked_bot_stops_that_wiki_only(app):
    meta, nl = _conversation('metawiki'), _conversation('nlwiki')
    for _ in range(3):
        _join(meta, _person(), email=False, talk=True)
    _join(nl, _person(), email=False, talk=True)
    _remind(meta)
    _remind(nl)

    def answer(**kw):
        if kw['wiki'] == 'metawiki':
            return Outcome('failed', reason='blocked', error_code='blocked')
        return Outcome('dry_run', sent_via=kw['wiki'])
    sender = Recording(answer)
    result = _run(sender)
    assert [call['wiki'] for call in sender.calls].count('metawiki') == 1
    assert result.blocked_wikis == {('talk', 'metawiki')}
    assert result.counts[('talk', 'failed')] == 3 and result.counts[('talk', 'dry_run')] == 1


# ── Retention ─────────────────────────────────────────────────────────────────

def _sent_row(conv, when):
    reminder = _remind(conv)
    joined = _join(conv, _person())
    row = ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                           channel='email', status='sent', claimed_at=when, attempted_at=when)
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize('ended', [{'active': False}, {'active': False, 'closed_at': NOW}])
def test_rows_are_unlinked_two_weeks_after_the_last_message_of_an_ended_consultation(app, ended):
    conv = _conversation(**ended)
    row = _sent_row(conv, NOW - timedelta(days=15))
    assert unlink_ended(NOW) == 1
    db.session.refresh(row)
    assert (row.participation_id, row.claimed_at, row.attempted_at) == (None, None, None)
    assert row.status == 'sent'      # the totals stay


def test_rows_stay_linked_until_two_weeks_have_passed(app):
    conv = _conversation(active=False)
    row = _sent_row(conv, NOW - timedelta(days=13))
    assert unlink_ended(NOW) == 0
    db.session.refresh(row)
    assert row.participation_id is not None


def test_rows_of_a_running_consultation_stay_linked(app):
    conv = _conversation()
    row = _sent_row(conv, NOW - timedelta(days=60))
    assert unlink_ended(NOW) == 0
    db.session.refresh(row)
    assert row.participation_id is not None


# ── Command ───────────────────────────────────────────────────────────────────

def test_the_command_reports_counts_and_names_nobody(app, monkeypatch):
    conv = _conversation(phase_submission=True)
    person = _person()
    _join(conv, person)
    reminder = _remind(conv, day=datetime.now(timezone.utc).date())
    monkeypatch.setitem(app.config, 'REMINDERS_EMAIL_DAILY_CAP', 5)
    result = app.test_cli_runner().invoke(args=['process-reminders', '--reminder', str(reminder.id)])
    assert result.exit_code == 0, result.output
    assert 'email dry_run: 1' in result.output
    assert person.mw_username not in result.output


def test_the_command_stops_when_paused(app, monkeypatch):
    monkeypatch.setitem(app.config, 'REMINDERS_PAUSED', True)
    result = app.test_cli_runner().invoke(args=['process-reminders'])
    assert result.exit_code == 0 and 'paused' in result.output
