"""A super admin's dry run of one reminder to a consultation's staff only (#576, step 1)."""

from datetime import date, datetime

import pytest

from db import (AdminRole, AuditEvent, Conversation, Participant, Participation, Reminder,
                ReminderDelivery, db)
from services.reminder_batch import Outcome, run_batch
from services.reminders import PHASE_OPENED, staff_participant_ids
from tests.conftest import _xid, login

_ids = iter(range(20000, 30000))


@pytest.fixture
def conv(app):
    conv = Conversation(slug='staff-run', polis_id='staffrun01', title='Staff run',
                        active=True, access_policy='public', reminder_wiki='nlwiki',
                        phase_submission=True)
    db.session.add(conv)
    db.session.commit()
    return conv


def _person(**fields):
    n = next(_ids)
    person = Participant(mw_user_id=n, mw_username=f'User{n}', xid=_xid(n), **fields)
    db.session.add(person)
    db.session.commit()
    return person


def _join(conv, person, *, email=True, talk=False):
    joined = Participation(participant_id=person.id, conversation_id=conv.id,
                           pseudonym=f'p{next(_ids)}', notify_email=email, notify_talk_page=talk)
    db.session.add(joined)
    db.session.commit()
    return joined


def _role(conv, person, role):
    db.session.add(AdminRole(participant_id=person.id, conversation_id=conv.id, role=role))
    db.session.commit()


class Recording:
    def __init__(self):
        self.calls = []

    def send(self, **kw):
        self.calls.append(kw)
        return Outcome('dry_run', sent_via=kw['wiki'])


# ── Who counts as staff ───────────────────────────────────────────────────────

def test_staff_are_role_holders_and_super_admins(app, conv):
    organizer, moderator, participant = _person(), _person(), _person()
    site_admin = _person(is_global_admin=True)
    configured = _person()
    other = Conversation(slug='other', polis_id='other00001', title='Other', active=True)
    db.session.add(other)
    db.session.commit()
    _role(conv, organizer, 'organizer')
    _role(conv, moderator, 'moderator')
    _role(other, participant, 'organizer')        # staff elsewhere, not here
    staff = staff_participant_ids(conv, admin_usernames=[configured.mw_username])
    assert staff == {organizer.id, moderator.id, site_admin.id, configured.id}


# ── The batch, limited to staff ───────────────────────────────────────────────

def _staff_run(conv, reminder, sender, audience):
    return run_batch(date(2026, 11, 20), now=datetime(2026, 11, 20, 9), sender=sender,
                     active_phases=lambda c: {'submission'}, email_cap=20, approved={},
                     reminder_id=reminder.id, triggered_by_id=1, audience=audience)


def test_audience_limits_the_recipients_to_staff_who_opted_in(app, conv):
    ticked, unticked, participant = _person(), _person(), _person()
    _role(conv, ticked, 'organizer')
    _role(conv, unticked, 'moderator')
    _join(conv, ticked, email=True, talk=True)
    _join(conv, unticked, email=False, talk=False)    # staff, never ticked: nothing
    _join(conv, participant, email=True, talk=True)   # ticked, not staff: nothing
    reminder = Reminder(conversation_id=conv.id, reminder_type=PHASE_OPENED,
                        phase_key='submission', send_day=date(2026, 11, 20))
    db.session.add(reminder)
    db.session.commit()
    sender = Recording()
    _staff_run(conv, reminder, sender, audience=lambda c: {ticked.id, unticked.id})
    rows = ReminderDelivery.query.filter_by(reminder_id=reminder.id).all()
    assert sorted((r.participation.participant_id, r.channel, r.status) for r in rows) == [
        (ticked.id, 'email', 'dry_run'), (ticked.id, 'talk', 'dry_run')]
    assert {call['participation'].participant_id for call in sender.calls} == {ticked.id}


# ── The API ───────────────────────────────────────────────────────────────────

STATE = '/api/v1/admin/conversations/{}/reminder-dry-run'
RUN = '/api/v1/admin/conversations/{}/reminder-dry-runs'


@pytest.fixture
def staff(app, conv):
    """An organizer who ticked wiki-mail, a moderator who ticked nothing, a participant."""
    organizer, moderator, participant = _person(), _person(), _person()
    _role(conv, organizer, 'organizer')
    _role(conv, moderator, 'moderator')
    _join(conv, organizer, email=True, talk=False)
    _join(conv, moderator, email=False, talk=False)
    _join(conv, participant, email=True, talk=True)
    return {'organizer': organizer, 'moderator': moderator, 'participant': participant}


@pytest.mark.parametrize('who', ['organizer', 'moderator', 'participant'])
def test_only_super_admins_may_see_or_run_it(client, conv, staff, who):
    login(client, staff[who].mw_username)
    assert client.get(STATE.format(conv.id)).status_code == 403
    response = client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert response.status_code == 403
    assert Reminder.query.count() == 0 and ReminderDelivery.query.count() == 0


def test_state_counts_staff_per_channel_and_says_whether_the_wiki_is_approved(
        admin_client, conv, staff):
    data = admin_client.get(STATE.format(conv.id)).get_json()['data']
    # Results only go out once the consultation is closed, so it is not offered yet.
    assert data == {
        'wiki': 'nlwiki', 'wikiHost': 'nl.wikipedia.org', 'automatedSendApproved': False,
        'reminderTypes': ['phase_opened', 'phase_closing'],
        'counts': {'email': 1, 'talk': 0},
    }


def test_dry_run_records_dry_run_rows_for_staff_only_and_sends_nothing(
        admin_client, conv, staff, monkeypatch):
    import app as app_module

    def no_live_sender(*args, **kwargs):
        raise AssertionError('the dry run must not build a live sender')
    monkeypatch.setattr(app_module, 'default_client_factory', no_live_sender)

    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    assert data['rows'] == [{
        'username': staff['organizer'].mw_username, 'channel': 'email',
        'status': 'dry_run', 'reason': None, 'errorCode': None,
    }]
    reminder = Reminder.query.one()
    assert data['reminderId'] == reminder.id
    assert reminder.phase_key == 'submission' and reminder.triggered_by_id is not None
    assert [(r.channel, r.status) for r in ReminderDelivery.query] == [('email', 'dry_run')]
    event = AuditEvent.query.filter_by(operation='reminder.staff_dry_run').one()
    assert staff['organizer'].mw_username not in repr(event.detail)


def test_dry_run_of_the_same_moment_twice_is_refused(admin_client, conv, staff):
    assert admin_client.post(RUN.format(conv.id),
                             json={'reminderType': 'phase_opened'}).status_code == 200
    again = admin_client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert again.status_code == 409
    assert again.get_json()['error']['code'] == 'reminder_exists'
    assert Reminder.query.count() == 1


def test_dry_run_refuses_an_unknown_type(admin_client, conv, staff):
    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'unanswered'})
    assert response.status_code == 400
    assert Reminder.query.count() == 0


def test_dry_run_is_refused_while_reminders_are_paused(admin_client, app, conv, staff):
    app.config['REMINDERS_PAUSED'] = True
    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'reminders_paused'
    assert Reminder.query.count() == 0


def test_a_message_that_is_not_due_is_refused_and_records_nothing(admin_client, conv, staff):
    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'results'})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'not_due'
    assert Reminder.query.count() == 0


def test_a_run_that_would_reach_nobody_is_refused_and_records_nothing(admin_client, conv):
    organizer = _person()
    _role(conv, organizer, 'organizer')
    _join(conv, organizer, email=False, talk=False)
    _join(conv, _person(), email=True, talk=True)       # a participant who ticked
    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'no_recipients'
    assert Reminder.query.count() == 0


def test_a_busy_batch_leaves_nothing_behind(admin_client, conv, staff, monkeypatch):
    from services import reminder_staff_run
    from services.reminder_batch import BatchBusy

    def busy(*args, **kwargs):
        raise BatchBusy()
    monkeypatch.setattr(reminder_staff_run, 'run_batch', busy)
    response = admin_client.post(RUN.format(conv.id), json={'reminderType': 'phase_opened'})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'batch_busy'
    assert Reminder.query.count() == 0 and ReminderDelivery.query.count() == 0


def _scheduled_run(day):
    """The daily run, on a wiki where the bot is approved: it hands out what is due."""
    run_batch(day, now=datetime.combine(day, datetime.min.time()).replace(hour=23),
              active_phases=lambda c: {'submission'}, sender=Recording(), email_cap=20,
              approved={'nlwiki': '#581'})


def _non_staff_rows(staff):
    return [row for row in ReminderDelivery.query
            if row.participation.participant_id == staff['participant'].id]


def test_the_reminder_is_never_committed_unrecorded(admin_client, conv, staff):
    from sqlalchemy import event
    seen = []

    def check(session):
        if session.in_nested_transaction():
            return              # a savepoint release, not a commit others can see
        seen.append(Reminder.query.filter(Reminder.recorded_at.is_(None)).count())
    event.listen(db.session, 'before_commit', check)
    try:
        assert admin_client.post(RUN.format(conv.id),
                                 json={'reminderType': 'phase_opened'}).status_code == 200
    finally:
        event.remove(db.session, 'before_commit', check)
    assert seen and set(seen) == {0}


def test_a_later_scheduled_run_adds_no_participant(admin_client, conv, staff):
    assert admin_client.post(RUN.format(conv.id),
                             json={'reminderType': 'phase_opened'}).status_code == 200
    day = Reminder.query.one().send_day
    _scheduled_run(day)
    assert _non_staff_rows(staff) == []
    assert [(r.channel, r.status) for r in ReminderDelivery.query] == [('email', 'dry_run')]


def test_an_interrupted_run_leaves_no_row_for_a_later_run(app, conv, staff, admin_participant,
                                                           monkeypatch):
    from services import reminder_staff_run

    def interrupted(*args, **kwargs):
        raise SystemExit(1)
    monkeypatch.setattr(reminder_staff_run, 'run_batch', interrupted)
    now = datetime(2026, 11, 20, 9)
    with pytest.raises(SystemExit):
        reminder_staff_run.run_staff_dry_run(
            conv, PHASE_OPENED, phase_key='submission', now=now,
            triggered_by=admin_participant, admin_usernames=[],
            active_phases=lambda c: {'submission'}, email_cap=20, paused=False)
    reminder = Reminder.query.one()
    assert reminder.recorded_at is not None
    assert [(r.channel, r.status) for r in ReminderDelivery.query] == [
        ('email', 'skipped_expired')]
    monkeypatch.undo()
    _scheduled_run(now.date())
    _scheduled_run(date(2026, 11, 21))
    assert _non_staff_rows(staff) == []
    assert ReminderDelivery.query.filter_by(status='pending').count() == 0
