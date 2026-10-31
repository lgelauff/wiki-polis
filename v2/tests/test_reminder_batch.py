"""The daily reminder batch, in dry-run (#577)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from db import Conversation, Participant, Participation, Reminder, ReminderDelivery, db
from services.reminder_batch import (
    DryRunSender, Outcome, ReminderNotFound, UnknownReminderWiki, run_batch, unlink_ended,
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
    phase = phase or ''
    reminder = Reminder(conversation_id=conv.id, reminder_type=kind, phase_key=phase,
                        send_day=day)
    db.session.add(reminder)
    db.session.commit()
    return reminder


def _run(sender=None, *, cap=20, approved=APPROVED, phases=None, **kw):
    phases = phases or (lambda conv: {'submission'})
    if kw.get('reminder_id') is not None:
        kw.setdefault('triggered_by_id', 1)
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
    assert result.totals[('email', 'dry_run')] == 2
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
    assert len(result.waiting_for_trigger) == 1 and result.due == []
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
    later = _remind(conv, phase='argument_mapping')
    sender = Recording()
    _run(sender, cap=2, reminder_id=later.id, phases=lambda c: {'argument_mapping'})
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
    assert result.totals[('talk', 'failed')] == 3 and result.totals[('talk', 'dry_run')] == 1


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

def test_the_command_reports_counts_and_names_nobody(app, monkeypatch, admin_participant):
    conv = _conversation(phase_submission=True)
    person = _person()
    _join(conv, person)
    reminder = _remind(conv, day=datetime.now(timezone.utc).date())
    monkeypatch.setitem(app.config, 'REMINDERS_EMAIL_DAILY_CAP', 5)
    result = app.test_cli_runner().invoke(args=['process-reminders', '--reminder', str(reminder.id),
                                                '--by', admin_participant.mw_username])
    assert result.exit_code == 0, result.output
    assert 'email dry_run: 1' in result.output
    assert person.mw_username not in result.output


def test_the_command_stops_when_paused(app, monkeypatch):
    monkeypatch.setitem(app.config, 'REMINDERS_PAUSED', True)
    result = app.test_cli_runner().invoke(args=['process-reminders'])
    assert result.exit_code == 0 and 'paused' in result.output


# ── Once only, triggers, unknown wikis (#587 review) ─────────────────────────

def test_a_recorded_reminder_is_never_recorded_again_even_after_unlinking(app):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv, kind=RESULTS, phase=None)
    closed = lambda c: {'closed'}
    first = Recording()
    _run(first, phases=closed)
    assert len(first.calls) == 1 and reminder.recorded_at == NOW
    ReminderDelivery.query.update({'participation_id': None, 'claimed_at': None,
                                   'attempted_at': None})
    db.session.commit()
    again = Recording()
    _run(again, phases=closed, reminder_id=reminder.id)
    assert again.calls == [] and ReminderDelivery.query.count() == 1


def test_a_super_admin_trigger_records_who_and_when(app, admin_participant):
    conv = _conversation(wiki='nlwiki')
    _join(conv, _person())
    reminder = _remind(conv)
    _run(approved={}, reminder_id=reminder.id, triggered_by_id=admin_participant.id)
    db.session.refresh(reminder)
    assert (reminder.triggered_by_id, reminder.triggered_at) == (admin_participant.id, NOW)


def test_the_scheduled_run_reports_a_wiki_the_bot_does_not_know(app):
    conv = _conversation(wiki='enwiki')
    _join(conv, _person())
    reminder = _remind(conv)
    sender = Recording()
    result = _run(sender, approved={'enwiki': 'x'})
    assert result.unknown_wiki == [reminder.id] and result.waiting_for_trigger == []
    assert sender.calls == [] and ReminderDelivery.query.count() == 0


def test_a_trigger_on_a_wiki_the_bot_does_not_know_is_refused(app):
    conv = _conversation(wiki='enwiki')
    reminder = _remind(conv)
    with pytest.raises(UnknownReminderWiki):
        _run(reminder_id=reminder.id)


def test_unlinking_also_clears_the_error_code_and_the_sending_wiki(app):
    conv = _conversation(active=False)
    row = _sent_row(conv, NOW - timedelta(days=15))
    row.status, row.reason, row.error_code = 'failed', 'api_error', 'readonly'
    db.session.commit()
    unlink_ended(NOW)
    db.session.refresh(row)
    assert (row.error_code, row.sent_via, row.participation_id) == (None, None, None)
    assert (row.channel, row.status, row.reason) == ('email', 'failed', 'api_error')


def test_rows_are_recorded_in_random_order(app):
    conv = _conversation()
    joined = [_join(conv, _person()) for _ in range(12)]
    reminder = _remind(conv)
    _run()
    by_id = [row.participation_id for row in
             ReminderDelivery.query.filter_by(reminder_id=reminder.id).order_by(ReminderDelivery.id)]
    assert sorted(by_id) == [j.id for j in joined]
    assert by_id != [j.id for j in joined]     # 1 in 12! to fail by chance


@pytest.mark.parametrize('reason', ['lagged', 'outcome_unknown'])
def test_the_bot_clients_own_reasons_are_recorded(app, reason):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv)
    _run(Recording(lambda **kw: Outcome('failed', reason=reason, error_code='timeout')))
    row = ReminderDelivery.query.filter_by(reminder_id=reminder.id).one()
    assert (row.status, row.reason, row.error_code) == ('failed', reason, 'timeout')


def test_the_command_records_the_super_admin_named_with_by(app, admin_participant):
    conv = _conversation(phase_submission=True)
    _join(conv, _person())
    reminder = _remind(conv, day=datetime.now(timezone.utc).date())
    result = app.test_cli_runner().invoke(args=[
        'process-reminders', '--reminder', str(reminder.id), '--by', admin_participant.mw_username])
    assert result.exit_code == 0, result.output
    db.session.refresh(reminder)
    assert reminder.triggered_by_id == admin_participant.id


def test_the_command_refuses_by_for_someone_who_is_not_a_super_admin(app, participant):
    conv = _conversation()
    reminder = _remind(conv)
    result = app.test_cli_runner().invoke(args=[
        'process-reminders', '--reminder', str(reminder.id), '--by', participant.mw_username])
    assert result.exit_code == 2 and 'super admin' in result.output


# ── Fixes from the B2 review ─────────────────────────────────────────────────

from db import ConversationBan  # noqa: E402
from services import reminder_batch  # noqa: E402
from services.reminder_batch import TriggerNeedsSuperAdmin, email_cap_from  # noqa: E402


def test_a_sender_that_raises_is_recorded_as_unknown_and_the_rest_still_goes(app):
    conv = _conversation()
    for _ in range(3):
        _join(conv, _person())
    reminder = _remind(conv)
    calls = []

    def answer(**kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('boom')
        return Outcome('dry_run', sent_via=kw['wiki'])
    _run(Recording(answer))
    assert sorted(s for _, s in _statuses(reminder)) == ['dry_run', 'dry_run', 'failed']
    failed = ReminderDelivery.query.filter_by(status='failed').one()
    assert failed.reason == 'outcome_unknown'


def test_an_outcome_the_log_cannot_hold_is_recorded_as_unknown(app):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv)
    _run(Recording(lambda **kw: Outcome('sent', reason='refused')))
    row = ReminderDelivery.query.filter_by(reminder_id=reminder.id).one()
    assert (row.status, row.reason) == ('failed', 'outcome_unknown')


def test_a_claim_left_unsettled_by_a_dead_run_becomes_unknown_and_is_never_resent(app):
    conv = _conversation()
    joined = _join(conv, _person())
    reminder = _remind(conv)
    reminder.recorded_at = NOW
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email', claimed_at=NOW - timedelta(hours=1)))
    db.session.commit()
    sender = Recording()
    result = _run(sender)
    assert result.stale_claims == 1 and sender.calls == []
    assert _statuses(reminder) == [('email', 'failed')]


def test_a_trigger_needs_the_super_admin_who_triggers_it(app):
    reminder = _remind(_conversation())
    with pytest.raises(TriggerNeedsSuperAdmin):
        run_batch(DAY, now=NOW, active_phases=lambda c: {'submission'}, sender=Recording(),
                  email_cap=5, reminder_id=reminder.id)


def test_the_first_trigger_is_kept_on_record(app):
    conv = _conversation(wiki='nlwiki')
    reminder = _remind(conv)
    _run(approved={}, reminder_id=reminder.id, triggered_by_id=7)
    run_batch(DAY, now=NOW + timedelta(hours=1), active_phases=lambda c: {'submission'},
              sender=Recording(), email_cap=5, approved={}, reminder_id=reminder.id,
              triggered_by_id=8)
    db.session.refresh(reminder)
    assert (reminder.triggered_by_id, reminder.triggered_at) == (7, NOW)


def test_one_message_per_person_per_day_holds_across_runs(app):
    person = _person()
    first, second = _conversation(), _conversation(wiki='nlwiki')
    _join(first, person)
    _join(second, person)
    _remind(first)
    later = _remind(second)
    _run(approved={'metawiki': '#582'})
    sender = Recording()
    _run(sender, approved={}, reminder_id=later.id)
    assert sender.calls == [] and _statuses(later) == [('email', 'not_sent_limit')]


def test_the_cap_counts_todays_mail_even_when_an_older_day_is_handled(app):
    conv = _conversation()
    for _ in range(2):
        _join(conv, _person())
    today = _remind(conv)
    _run(cap=1)                                         # one mail goes out today
    old = _remind(_conversation(), day=DAY - timedelta(days=1))
    _join(old.conversation, _person())
    sender = Recording()
    run_batch(DAY - timedelta(days=1), now=NOW, active_phases=lambda c: {'submission'},
              sender=sender, email_cap=1, approved=APPROVED)
    assert sender.calls == [] and _statuses(old) == [('email', 'not_sent_limit')]
    assert ('email', 'dry_run') in _statuses(today)


def test_failed_mail_does_not_use_up_the_cap(app):
    conv = _conversation()
    for _ in range(3):
        _join(conv, _person())
    reminder = _remind(conv)
    calls = []

    def answer(**kw):
        calls.append(1)
        return (Outcome('failed', reason='not_emailable') if len(calls) == 1
                else Outcome('dry_run', sent_via=kw['wiki']))
    _run(Recording(answer), cap=2)
    assert sorted(s for _, s in _statuses(reminder)) == ['dry_run', 'dry_run', 'failed']


def test_the_other_rows_share_the_primarys_outcome_when_it_was_not_delivered(app):
    person = _person()
    one, two = _conversation(), _conversation()
    _join(one, person)
    _join(two, person)
    first, second = _remind(one), _remind(two)
    _run(Recording(lambda **kw: Outcome('skipped_optout')))
    assert _statuses(first) == [('email', 'skipped_optout')]
    assert _statuses(second) == [('email', 'skipped_optout')]


def test_someone_banned_after_recording_is_not_messaged(app):
    conv = _conversation()
    joined = _join(conv, _person())
    reminder = _remind(conv)
    reminder_batch._record_deliveries(reminder, {'submission'}, NOW)
    db.session.add(ConversationBan(conversation_id=conv.id, participant_id=joined.participant_id))
    db.session.commit()
    sender = Recording()
    _run(sender)
    assert sender.calls == [] and _statuses(reminder) == [('email', 'skipped_optout')]


def test_a_reminder_that_expired_after_recording_is_not_sent(app):
    conv = _conversation()
    _join(conv, _person())
    reminder = _remind(conv)
    reminder_batch._record_deliveries(reminder, {'submission'}, NOW)
    sender = Recording()
    _run(sender, phases=lambda c: {'cleanup'})
    assert sender.calls == [] and _statuses(reminder) == [('email', 'skipped_expired')]


def test_a_missed_day_on_an_approved_wiki_is_dropped_as_expired(app):
    conv = _conversation()
    _join(conv, _person())
    missed = _remind(conv, day=DAY - timedelta(days=2))
    waiting = _remind(_conversation(wiki='nlwiki'), day=DAY - timedelta(days=2))
    sender = Recording()
    result = _run(sender, approved={'metawiki': '#582'})
    assert result.missed == [missed.id] and waiting.id in result.waiting_for_trigger
    assert sender.calls == [] and _statuses(missed) == [('email', 'skipped_expired')]
    assert waiting.recorded_at is None


def test_pausing_mid_run_stops_the_rest(app):
    conv = _conversation()
    for _ in range(3):
        _join(conv, _person())
    reminder = _remind(conv)
    sender = Recording()
    checks = []

    def paused():
        checks.append(1)
        return len(sender.calls) >= 1 and len(checks) > 1
    _run(sender, paused=paused)
    assert len(sender.calls) == 1
    assert [s for _, s in _statuses(reminder)].count('pending') == 2


def test_retention_unlinks_waiting_rows_after_settling_them(app):
    conv = _conversation(active=False)
    reminder = _remind(conv)
    free, claimed = _join(conv, _person()), _join(conv, _person())
    db.session.add_all([
        ReminderDelivery(reminder_id=reminder.id, participation_id=free.id, channel='email'),
        ReminderDelivery(reminder_id=reminder.id, participation_id=claimed.id, channel='talk',
                         claimed_at=NOW - timedelta(days=20)),
    ])
    db.session.commit()
    assert unlink_ended(NOW) == 2
    rows = {r.channel: r for r in ReminderDelivery.query}
    assert rows['email'].status == 'skipped_expired'
    assert (rows['talk'].status, rows['talk'].reason) == ('failed', 'outcome_unknown')
    assert all(r.participation_id is None and r.claimed_at is None for r in rows.values())


def test_the_retention_clock_counts_only_messages_that_went_out(app):
    conv = _conversation(active=False)
    row = _sent_row(conv, NOW - timedelta(days=15))
    later = ReminderDelivery(reminder_id=row.reminder_id, participation_id=_join(conv, _person()).id,
                             channel='talk', status='not_sent_limit',
                             attempted_at=NOW - timedelta(days=1))
    db.session.add(later)
    db.session.commit()
    assert unlink_ended(NOW) == 2


@pytest.mark.parametrize('value, cap', [('', 5), ('7', 7), (' 3 ', 3), ('five', 5), ('-1', 5),
                                        ('50', 20), ('0', 0)])
def test_the_cap_setting_is_read_safely(value, cap):
    assert email_cap_from(value) == cap


def test_the_command_refuses_a_trigger_without_by(app):
    reminder = _remind(_conversation())
    result = app.test_cli_runner().invoke(args=['process-reminders', '--reminder', str(reminder.id)])
    assert result.exit_code == 2 and '--by' in result.output


def test_the_command_refuses_a_later_day(app):
    result = app.test_cli_runner().invoke(args=['process-reminders', '--day', '2999-01-01'])
    assert result.exit_code == 2


def test_the_command_refuses_while_another_run_holds_the_lock(app, monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def busy():
        raise reminder_batch.BatchBusy()
        yield
    monkeypatch.setattr(reminder_batch, 'single_flight', busy)
    result = app.test_cli_runner().invoke(args=['process-reminders'])
    assert result.exit_code == 2 and 'in progress' in result.output


def test_a_run_that_breaks_off_exits_3(app, monkeypatch):
    def broken(*a, **kw):
        raise RuntimeError('db gone')
    monkeypatch.setattr('app.run_reminder_batch', broken)
    result = app.test_cli_runner().invoke(args=['process-reminders'])
    assert result.exit_code == 3
