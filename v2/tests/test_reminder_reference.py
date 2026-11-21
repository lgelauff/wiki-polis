"""The reference in every bot wiki-mail, and the super-admin lookup (#622)."""

import logging
import re
from datetime import datetime, timedelta, timezone

import pytest

from db import AuditEvent, Participant, ReminderDelivery, ReminderReferenceKey, db
from services import reminder_reference
from services.reminder_batch import DryRunSender, run_batch, unlink_ended
from services.reminder_messages import MessageSettings
from services.reminder_sender import LiveSender
from services.reminders import PHASE_CLOSING, PHASE_OPENED, RESULTS
from tests.conftest import login
from tests.test_reminder_batch import APPROVED, DAY, NOW, _conversation, _join, _person, _remind

LOOKUPS = '/api/v1/admin/reminder-reference-lookups'
NO_MATCH = {'match': False, 'kind': None, 'username': None, 'sendDay': None, 'items': []}
_REF = re.compile(r'Proto K\d+ [A-Z2-7]{9}-[A-Z2-7]{9}-[A-Z2-7]{8}')


class FakeWiki:
    """A wiki client that accepts every wiki-mail and talk post and keeps them."""

    def __init__(self, wiki, sent, posted):
        self.wiki, self.sent, self.posted = wiki, sent, posted

    def is_emailable(self, username):
        return True

    def send_email(self, username, *, subject, text):
        self.sent.append((username, subject, text))

    def talk_page_allows_bot(self, username):
        return True

    def talk_page_opted_out(self, username):
        return False

    def post_talk_section(self, username, *, title, text, summary):
        self.posted.append((username, title, text))


def _live(sent, posted=None):
    posted = [] if posted is None else posted
    return LiveSender(client_for=lambda wiki, channel: FakeWiki(wiki, sent, posted),
                      messages=MessageSettings(base_url='https://proto.example'))


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _batch(sender, now=NOW):
    return run_batch(now.date(), now=now, active_phases=lambda conv: {'submission'},
                     sender=sender, email_cap=20, approved=APPROVED)


def _unused_bits_set(reference: str) -> str:
    """The same reference with the last character's two unused bits set: it decodes to
    the same bytes, but it is not a reference Proto made."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    head, last = reference[:-1], reference[-1]
    return head + alphabet[alphabet.index(last) | 1]


def _altered(reference: str) -> str:
    """The same reference with one character of the code changed."""
    head, code = reference.rsplit(' ', 1)
    first = 'B' if code[0] != 'B' else 'C'
    return f'{head} {first}{code[1:]}'


# ── Making and reading a reference ────────────────────────────────────────────

def test_a_reference_decrypts_to_its_own_delivery(app, conversation, participant):
    joined = _join(conversation, participant)
    reminder = _remind(conversation)
    rows = [ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                             channel='email', status='sent')]
    other = _join(_conversation(), _person())
    rows.append(ReminderDelivery(reminder_id=_remind(other.conversation).id,
                                 participation_id=other.id, channel='email', status='sent'))
    db.session.add_all(rows)
    db.session.commit()

    for row in rows:
        found = reminder_reference.lookup(reminder_reference.for_delivery(row.id, NOW), NOW)
        assert found.kind == 'reminder'
        assert found.username == row.participation.participant.mw_username
        assert found.send_day == DAY
        assert [i.conversation_id for i in found.items] == [row.reminder.conversation_id]
        assert found.items[0].reminder_type == PHASE_OPENED


def test_a_reference_carries_no_username_or_number_and_fits_the_mail(app, conversation, participant):
    row = ReminderDelivery(reminder_id=_remind(conversation).id,
                           participation_id=_join(conversation, participant).id,
                           channel='email', status='sent')
    db.session.add(row)
    db.session.commit()
    reference = reminder_reference.for_delivery(row.id, NOW)
    assert _REF.fullmatch(reference)
    assert participant.mw_username.upper() not in reference.upper()
    assert str(participant.mw_user_id) not in reference
    # Pasted in another case, or inside the line it came in, it still matches.
    assert reminder_reference.lookup(f'Reference: {reference.lower()} thanks', NOW) is not None


@pytest.mark.parametrize('make', [
    lambda ref: 'Proto K1 ABCDEFGHI-JKLMNOPQR-STUVWXYZ',      # made up
    _altered,                                                # one character changed
    lambda ref: ref.replace(' K1 ', ' K2 '),                 # another key's label
    lambda ref: ref[:-1],                                    # cut short
    _unused_bits_set,
    lambda ref: '',
])
def test_a_made_up_or_altered_reference_matches_nothing(app, conversation, participant, make):
    row = ReminderDelivery(reminder_id=_remind(conversation).id,
                           participation_id=_join(conversation, participant).id,
                           channel='email', status='sent')
    db.session.add(row)
    db.session.commit()
    reference = reminder_reference.for_delivery(row.id, NOW)
    assert reference.startswith('Proto K1 ')
    # Two keys exist, so a changed label points at a real key that does not fit.
    reminder_reference.for_test_send(NOW + timedelta(days=31))
    assert reminder_reference.lookup(make(reference), NOW) is None


def test_a_reference_to_a_talk_page_delivery_matches_nothing(app, conversation, participant):
    row = ReminderDelivery(reminder_id=_remind(conversation).id,
                           participation_id=_join(conversation, participant).id,
                           channel='talk', status='sent')
    db.session.add(row)
    db.session.commit()
    assert reminder_reference.lookup(reminder_reference.for_delivery(row.id, NOW), NOW) is None


def test_a_reference_whose_delivery_is_gone_matches_nothing(app):
    assert reminder_reference.lookup(reminder_reference.for_delivery(424242, NOW), NOW) is None


def test_a_test_send_reference_gives_its_day(app):
    found = reminder_reference.lookup(reminder_reference.for_test_send(NOW), NOW)
    assert (found.kind, found.send_day, found.username, found.items) == (
        'test_send', NOW.date(), None, [])


# ── Keys ──────────────────────────────────────────────────────────────────────

def test_keys_rotate_monthly(app):
    november = reminder_reference.for_test_send(datetime(2026, 11, 2))
    again = reminder_reference.for_test_send(datetime(2026, 11, 30))
    december = reminder_reference.for_test_send(datetime(2026, 12, 1))
    assert november.split()[1] == again.split()[1] != december.split()[1]
    assert sorted(k.month for k in ReminderReferenceKey.query) == ['2026-11', '2026-12']
    november_key = ReminderReferenceKey.query.filter_by(month='2026-11').one()
    assert november_key.last_used_at == datetime(2026, 11, 30)


def test_a_key_is_deleted_90_days_after_its_last_use(app):
    reference = reminder_reference.for_test_send(datetime(2026, 11, 30))
    last_use = datetime(2026, 11, 30)
    assert reminder_reference.delete_unused_keys(last_use + timedelta(days=90)) == 0
    assert reminder_reference.lookup(reference, last_use + timedelta(days=90)) is not None
    later = last_use + timedelta(days=90, seconds=1)
    assert reminder_reference.delete_unused_keys(later) == 1
    assert ReminderReferenceKey.query.count() == 0
    assert reminder_reference.lookup(reference, later) is None


def test_a_key_past_90_days_is_not_used_even_before_the_job_deletes_it(app):
    reference = reminder_reference.for_test_send(NOW)
    assert reminder_reference.lookup(reference, NOW + timedelta(days=91)) is None


def test_the_daily_batch_deletes_unused_keys(app):
    reminder_reference.for_test_send(NOW - timedelta(days=120))
    result = _batch(DryRunSender())
    assert result.reference_keys_deleted == 1
    assert ReminderReferenceKey.query.count() == 0


# ── In the mail ───────────────────────────────────────────────────────────────

def test_every_reminder_mail_carries_its_reference_in_subject_and_last_line(app):
    conv, person = _conversation(), _person()
    _join(conv, person, email=True, talk=True)
    _remind(conv)
    sent, posted = [], []
    with _live(sent, posted) as sender:
        _batch(sender)
    [(username, subject, body)] = sent
    reference = _REF.search(subject).group(0)
    assert subject.endswith(f'[{reference}]')
    assert body.splitlines()[-1] == f'Reference: {reference}'
    # Talk-page notes are public and carry no reference.
    [(_, title, text)] = posted
    assert 'Proto K' not in title + text and 'Reference' not in text
    assert ReminderDelivery.query.filter_by(channel='email').one().status == 'sent'
    assert reminder_reference.lookup(reference, NOW).username == person.mw_username


def test_a_reply_to_a_combined_mail_traces_to_every_delivery_in_it(app):
    person = _person()
    convs = [_conversation() for _ in range(3)]
    for conv, kind in zip(convs, (PHASE_OPENED, PHASE_CLOSING, RESULTS)):
        _join(conv, person)
        _remind(conv, kind=kind, phase='' if kind == RESULTS else 'submission')
    sent = []
    with _live(sent) as sender:
        _batch(sender, now=NOW)
    # RESULTS expires before the close, so two reminders are left, in one mail.
    [(_, subject, body)] = sent
    found = reminder_reference.lookup(subject, NOW)
    rows = ReminderDelivery.query.filter(ReminderDelivery.status.in_(('sent', 'combined'))).all()
    assert len(rows) == 2
    assert sorted(i.conversation_id for i in found.items) == sorted(
        r.reminder.conversation_id for r in rows)
    first = next(r for r in rows if r.status == 'sent')
    assert [r.combined_into_id for r in rows if r.status == 'combined'] == [first.id]


def test_a_dry_run_makes_no_reference(app):
    conv = _conversation()
    _join(conv, _person())
    _remind(conv)
    _batch(DryRunSender())
    assert ReminderReferenceKey.query.count() == 0


def test_a_wiki_mail_without_a_reference_is_never_sent(app):
    conv, person = _conversation(), _person()
    joined = _join(conv, person)
    reminder = _remind(conv)
    sent = []
    with _live(sent) as sender:
        outcome = sender.send(channel='email', wiki='metawiki', participation=joined,
                              reminders=[reminder])
    assert outcome.status == 'failed' and sent == []


# ── Who the reference leads to ────────────────────────────────────────────────

def _sent_row(conv=None, person=None):
    conv, person = conv or _conversation(), person or _person()
    row = ReminderDelivery(reminder_id=_remind(conv).id,
                           participation_id=_join(conv, person).id,
                           channel='email', status='sent', attempted_at=NOW)
    db.session.add(row)
    db.session.commit()
    return row, person


def test_a_renamed_account_shows_its_current_username(app):
    row, person = _sent_row()
    reference = reminder_reference.for_delivery(row.id, NOW)
    person.mw_username = 'Renamed person'       # what the next sign-in stores
    db.session.commit()
    assert reminder_reference.lookup(reference, NOW).username == 'Renamed person'


def test_an_unlinked_delivery_shows_unknown(app):
    conv = _conversation(active=False)
    row, _ = _sent_row(conv)
    reference = reminder_reference.for_delivery(row.id, NOW)
    assert unlink_ended(NOW + timedelta(days=15)) == 1
    found = reminder_reference.lookup(reference, NOW + timedelta(days=15))
    assert found.username is None and found.items[0].conversation_id == conv.id


# ── The lookup box ────────────────────────────────────────────────────────────

def test_a_valid_reference_shows_its_delivery(admin_client):
    row, person = _sent_row()
    reference = reminder_reference.for_delivery(row.id, _now())
    data = admin_client.post(LOOKUPS, json={'reference': reference}).get_json()['data']
    assert data == {
        'match': True, 'kind': 'reminder', 'username': person.mw_username,
        'sendDay': DAY.isoformat(),
        'items': [{'conversationId': row.reminder.conversation_id,
                   'title': row.reminder.conversation.title, 'reminderType': PHASE_OPENED}],
    }


def test_made_up_altered_and_expired_references_get_the_same_no_match(admin_client):
    now = _now()
    row, _ = _sent_row()
    valid = reminder_reference.for_delivery(row.id, now)
    expired = reminder_reference.for_test_send(now - timedelta(days=200))
    answers = [admin_client.post(LOOKUPS, json={'reference': text})
               for text in ('Proto K1 ABCDEFGHI-JKLMNOPQR-STUVWXYZ', _altered(valid), expired,
                            'hello')]
    assert {r.status_code for r in answers} == {200}
    assert [r.get_json() for r in answers] == [{'data': NO_MATCH}] * 4
    assert {r.headers.get('Cache-Control') for r in answers} == {
        answers[0].headers.get('Cache-Control')}


def test_nobody_else_can_use_the_lookup(client, participant):
    row, _ = _sent_row()
    reference = reminder_reference.for_delivery(row.id, _now())
    assert client.post(LOOKUPS, json={'reference': reference}).status_code == 401
    login(client, participant.mw_username)
    response = client.post(LOOKUPS, json={'reference': reference})
    assert response.status_code == 403
    assert participant.mw_username not in response.get_data(as_text=True)
    assert AuditEvent.query.filter_by(operation='reminder.reference_lookup').count() == 0


def test_an_organizer_cannot_use_the_lookup(client, participant):
    from db import AdminRole
    row, _ = _sent_row()
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=row.reminder.conversation_id, role='organizer'))
    db.session.commit()
    login(client, participant.mw_username)
    reference = reminder_reference.for_delivery(row.id, _now())
    assert client.post(LOOKUPS, json={'reference': reference}).status_code == 403


def test_each_lookup_is_recorded_with_who_and_when_only(admin_client, admin_participant, caplog):
    row, person = _sent_row()
    reference = reminder_reference.for_delivery(row.id, _now())
    caplog.set_level(logging.DEBUG)
    for text in (reference, 'Proto K9 ABCDEFGHI-JKLMNOPQR-STUVWXYZ'):
        admin_client.post(LOOKUPS, json={'reference': text})
    events = AuditEvent.query.filter_by(operation='reminder.reference_lookup').all()
    assert len(events) == 2
    for event in events:
        assert event.actor_participant_id == admin_participant.id and event.ts is not None
        assert (event.detail, event.target_type, event.target_id, event.conversation_id,
                event.outcome) == ({}, None, None, None, 'ok')
    code = reference.rsplit(' ', 1)[1]
    for text in (code, person.mw_username, 'ABCDEFGHI'):
        assert text not in caplog.text


def test_a_lookup_request_must_hold_only_a_reference(admin_client):
    for body in ({}, {'reference': ''}, {'reference': 5}, {'reference': 'x' * 2001},
                 {'reference': 'x', 'more': 1}):
        assert admin_client.post(LOOKUPS, json=body).status_code == 400


# ── Migration ─────────────────────────────────────────────────────────────────

def test_the_migration_adds_the_key_table_and_the_pointer_and_downgrades_cleanly():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from tests.test_reminders_core import _migration as reminders_migration

    path = (Path(__file__).parents[1] / 'migrations' / 'versions'
            / 'b8c9d0e1f2a3_add_reminder_reference_keys.py')
    spec = spec_from_file_location('reference_migration', path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == 'a7b8c9d0e1f2'

    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('conversations', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('participants', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('participations', metadata, sa.Column('id', sa.Integer, primary_key=True))
    with engine.begin() as conn:
        metadata.create_all(conn)
        ops = Operations(MigrationContext.configure(conn))
        before = reminders_migration()
        before.op = ops
        before.upgrade()
        migration.op = ops
        migration.upgrade()
        inspector = sa.inspect(conn)
        assert {c['name'] for c in inspector.get_columns('reminder_reference_keys')} == {
            'id', 'month', 'key', 'created_at', 'last_used_at'}
        assert 'combined_into_id' in {c['name'] for c in
                                      inspector.get_columns('reminder_deliveries')}
        conn.execute(sa.text("INSERT INTO reminder_reference_keys (month, key, created_at, "
                             "last_used_at) VALUES ('2026-11', x'00', '2026-11-01', "
                             "'2026-11-01')"))
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(sa.text("INSERT INTO reminder_reference_keys (month, key, "
                                     "created_at, last_used_at) VALUES ('2026-11', x'01', "
                                     "'2026-11-01', '2026-11-01')"))
        migration.downgrade()
        inspector = sa.inspect(conn)
        assert 'reminder_reference_keys' not in inspector.get_table_names()
        assert 'combined_into_id' not in {c['name'] for c in
                                          inspector.get_columns('reminder_deliveries')}
