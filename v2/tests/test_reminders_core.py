"""Reminder sender core, part 1 (#577): tables, per-wiki settings, permission, recipients, expiry."""

from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

import db as db_module
from db import (
    ACCOUNT_KIND_VOUCHER, Conversation, ConversationBan, Participant, Participation, Reminder,
    ReminderDelivery, db,
)
from services import reminder_wikis, wiki_bot
from services.reminders import (
    PHASE_CLOSING, PHASE_OPENED, RESULTS, can_send_reminders, is_expired, recipients,
)
from tests.conftest import _xid


# ── Per-wiki settings ─────────────────────────────────────────────────────────

def test_no_wiki_is_approved_for_automatic_sends_yet():
    assert reminder_wikis.AUTOMATED_SEND_WIKIS == {}
    assert not any(reminder_wikis.is_approved(w) for w in reminder_wikis.known_wikis())


@pytest.mark.parametrize('wiki', ['metawiki', 'nlwiki'])
def test_talk_posts_are_ten_seconds_apart_where_the_bot_is_not_approved(wiki):
    assert reminder_wikis.talk_edit_interval(wiki) == 10.0


def test_talk_posts_are_two_seconds_apart_once_approved():
    assert reminder_wikis.talk_edit_interval('nlwiki', approved={'nlwiki': '#581'}) == 2.0


def test_meta_keeps_five_seconds_once_approved_as_its_bot_policy_asks():
    assert reminder_wikis.talk_edit_interval('metawiki', approved={'metawiki': '#582'}) == 5.0


def test_a_per_wiki_value_overrides_each_default(monkeypatch):
    monkeypatch.setitem(reminder_wikis.WIKI_SETTINGS, 'nlwiki', reminder_wikis.WikiSettings(
        talk_edit_interval_not_approved=30.0, talk_edit_interval_approved=6.0))
    assert reminder_wikis.talk_edit_interval('nlwiki') == 30.0
    assert reminder_wikis.talk_edit_interval('nlwiki', approved={'nlwiki': '#581'}) == 6.0


def test_every_wiki_with_settings_is_one_the_bot_knows():
    assert set(reminder_wikis.WIKI_SETTINGS) <= set(reminder_wikis.known_wikis())
    assert reminder_wikis.DEFAULT_REMINDER_WIKI in reminder_wikis.known_wikis()


def test_an_unknown_wiki_has_no_interval():
    with pytest.raises(ValueError):
        reminder_wikis.talk_edit_interval('enwiki')


# ── Permission ────────────────────────────────────────────────────────────────

def test_only_super_admins_can_send(participant, admin_participant, conversation):
    assert can_send_reminders(admin_participant, conversation)
    assert not can_send_reminders(participant, conversation)
    assert not can_send_reminders(None, conversation)


def test_a_configured_admin_username_counts_as_super_admin(participant, conversation):
    assert can_send_reminders(participant, conversation, admin_usernames=['testuser'])


# ── Recipients ────────────────────────────────────────────────────────────────

_next_id = iter(range(1000, 2000))


def _join(conversation, *, email=False, talk=False, **participant_fields):
    uid = next(_next_id)
    fields = {'mw_user_id': uid, 'mw_username': f'User{uid}', 'xid': _xid(uid)}
    fields.update(participant_fields)
    person = Participant(**fields)
    db.session.add(person)
    db.session.flush()
    joined = Participation(participant_id=person.id, conversation_id=conversation.id,
                           pseudonym=f'p{uid}', notify_email=email, notify_talk_page=talk)
    db.session.add(joined)
    db.session.commit()
    return joined


def test_recipients_are_those_who_ticked_the_channel(conversation):
    both = _join(conversation, email=True, talk=True)
    mail_only = _join(conversation, email=True)
    talk_only = _join(conversation, talk=True)
    _join(conversation)
    assert recipients(conversation, 'email') == [both, mail_only]
    assert recipients(conversation, 'talk') == [both, talk_only]


def test_access_code_and_demo_accounts_are_never_recipients(conversation):
    _join(conversation, email=True, talk=True, mw_user_id=None, mw_username=None,
          account_kind=ACCOUNT_KIND_VOUCHER, conversation_id=conversation.id)
    _join(conversation, email=True, talk=True, is_demo=True)
    assert recipients(conversation, 'email') == []
    assert recipients(conversation, 'talk') == []


def test_a_banned_participant_is_not_a_recipient_until_the_ban_is_lifted(conversation):
    joined = _join(conversation, email=True)
    ban = ConversationBan(conversation_id=conversation.id, participant_id=joined.participant_id)
    db.session.add(ban)
    db.session.commit()
    assert recipients(conversation, 'email') == []
    ban.lifted_at = datetime.now(timezone.utc)
    db.session.commit()
    assert recipients(conversation, 'email') == [joined]


def test_recipients_are_per_consultation(conversation):
    other = Conversation(slug='other', polis_id='other12345', title='Other', active=True)
    db.session.add(other)
    db.session.commit()
    _join(other, email=True)
    assert recipients(conversation, 'email') == []


def test_an_unknown_channel_is_refused(conversation):
    with pytest.raises(ValueError):
        recipients(conversation, 'sms')


# ── Expiry ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('kind', [PHASE_OPENED, PHASE_CLOSING])
def test_a_phase_reminder_is_live_while_its_phase_is_on(kind):
    assert not is_expired(kind, 'argument_mapping', {'argument_mapping'})


@pytest.mark.parametrize('kind', [PHASE_OPENED, PHASE_CLOSING])
def test_a_phase_reminder_expires_once_a_later_phase_opened(kind):
    assert is_expired(kind, 'argument_mapping', {'cleanup'})


@pytest.mark.parametrize('kind', [PHASE_OPENED, PHASE_CLOSING])
def test_a_phase_reminder_expires_when_the_consultation_closed(kind):
    assert is_expired(kind, 'argument_mapping', {'argument_mapping', 'closed'})


def test_the_final_message_waits_for_the_close():
    assert is_expired(RESULTS, None, {'public_results'})
    assert not is_expired(RESULTS, None, {'public_results', 'closed'})


def test_a_phase_reminder_without_a_phase_or_an_unknown_type_is_refused():
    with pytest.raises(ValueError):
        is_expired(PHASE_OPENED, None, {'submission'})
    with pytest.raises(ValueError):
        is_expired('unanswered', None, {'submission'})


# ── Tables ────────────────────────────────────────────────────────────────────

def test_a_consultation_sends_from_meta_by_default_and_does_not_name_itself(conversation):
    assert conversation.reminder_wiki == 'metawiki'
    assert conversation.reminder_talk_names_consultation is False


def _reminder(conversation, **fields):
    reminder = Reminder(conversation_id=conversation.id, reminder_type=PHASE_OPENED,
                        phase_key='submission', send_day=date(2026, 11, 2), **fields)
    db.session.add(reminder)
    db.session.commit()
    return reminder


def test_one_delivery_per_participation_and_channel(conversation):
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email'))
    db.session.commit()
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('fields', [
    {'status': 'failed'},                              # a failure needs its reason
    {'status': 'failed', 'reason': 'unknown'},         # from the closed list
    {'status': 'sent', 'reason': 'refused'},           # only failures have one
    {'status': 'delivered'},                           # unknown status
    {'channel': 'sms'},                                # unknown channel
])
def test_delivery_rows_keep_to_the_closed_vocabulary(conversation, fields):
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    row = {'reminder_id': reminder.id, 'participation_id': joined.id, 'channel': 'email'}
    row.update(fields)
    db.session.add(ReminderDelivery(**row))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_one_reminder_per_moment_including_the_final_message(conversation):
    _reminder(conversation)
    db.session.add(Reminder(conversation_id=conversation.id, reminder_type=PHASE_OPENED,
                            phase_key='submission', send_day=date(2026, 11, 2)))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    for _ in range(2):
        db.session.add(Reminder(conversation_id=conversation.id, reminder_type=RESULTS,
                                send_day=date(2026, 11, 9)))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_same_type_on_another_day_or_phase_is_another_reminder(conversation):
    _reminder(conversation)
    for fields in ({'phase_key': 'submission', 'send_day': date(2026, 11, 3)},
                   {'phase_key': 'argument_mapping', 'send_day': date(2026, 11, 2)}):
        db.session.add(Reminder(conversation_id=conversation.id, reminder_type=PHASE_OPENED,
                                **fields))
    db.session.commit()
    assert Reminder.query.count() == 3


def test_every_reason_the_bot_client_raises_can_be_recorded():
    raised = {value for name, value in vars(wiki_bot).items()
              if name.isupper() and isinstance(value, str) and value.islower()
              and name not in ('FALLBACK_WIKI',)}
    assert raised <= set(db_module.REMINDER_FAILURE_REASONS)


@pytest.mark.parametrize('values, column', [
    (db_module.REMINDER_CHANNELS, ReminderDelivery.__table__.c.channel),
    (db_module.REMINDER_DELIVERY_STATUSES, ReminderDelivery.__table__.c.status),
    (db_module.REMINDER_FAILURE_REASONS, ReminderDelivery.__table__.c.reason),
])
def test_every_closed_list_value_fits_its_column(values, column):
    # MariaDB in strict mode refuses a longer value; SQLite does not check.
    assert max(len(v) for v in values) <= column.type.length


def test_an_error_code_is_kept_only_on_a_failure(conversation):
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email', status='sent', error_code='x'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('reason', ['lagged', 'outcome_unknown'])
def test_the_client_only_reasons_are_accepted(conversation, reason):
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email', status='failed', reason=reason,
                                    error_code='timeout'))
    db.session.commit()


def test_a_failed_delivery_records_its_reason(conversation):
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email', status='failed', reason='refused'))
    db.session.commit()


def test_an_unlinked_delivery_keeps_counting_in_the_totals(conversation):
    reminder = _reminder(conversation)
    first, second = _join(conversation, email=True), _join(conversation, email=True)
    for joined in (first, second):
        db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                        channel='email', status='sent', sent_via='metawiki',
                                        attempted_at=datetime.now(timezone.utc)))
    db.session.commit()
    ReminderDelivery.query.update({'participation_id': None, 'claimed_at': None,
                                   'attempted_at': None})
    db.session.commit()
    totals = db.session.query(ReminderDelivery.status, sa.func.count()).filter_by(
        reminder_id=reminder.id).group_by(ReminderDelivery.status).all()
    assert totals == [('sent', 2)]


def test_deleting_a_consultation_deletes_its_reminders(admin_client, conversation):
    from unittest.mock import MagicMock, patch
    reminder = _reminder(conversation)
    joined = _join(conversation, email=True)
    db.session.add(ReminderDelivery(reminder_id=reminder.id, participation_id=joined.id,
                                    channel='email'))
    db.session.commit()
    server = MagicMock()
    server.get_valid_vote_count.return_value = 0
    with patch('app._polis_server_client', return_value=server):
        response = admin_client.delete(f'/api/v1/admin/conversations/{conversation.id}')
    assert response.status_code == 200
    assert Reminder.query.count() == 0 and ReminderDelivery.query.count() == 0


def test_no_reminder_table_stores_a_username_or_message_text():
    for model in (Reminder, ReminderDelivery):
        names = {c.name for c in model.__table__.columns}
        assert not any(word in name for name in names
                       for word in ('username', 'text', 'body', 'subject'))


# ── Migration ─────────────────────────────────────────────────────────────────

MIGRATION_PATH = (Path(__file__).parents[1] / 'migrations' / 'versions'
                  / 'a7b8c9d0e1f2_add_reminders.py')


def _migration():
    spec = spec_from_file_location('reminders_migration', MIGRATION_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_upgrades_and_downgrades_cleanly():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('conversations', metadata, sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('title', sa.String(255)))
    sa.Table('participants', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('participations', metadata, sa.Column('id', sa.Integer, primary_key=True))
    migration = _migration()
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(sa.text("INSERT INTO conversations (id, title) VALUES (1, 'Old')"))
        ops = Operations(MigrationContext.configure(conn))
        migration.op = ops
        migration.upgrade()
        inspector = sa.inspect(conn)
        assert {'reminders', 'reminder_deliveries'} <= set(inspector.get_table_names())
        row = conn.execute(sa.text(
            'SELECT reminder_wiki, reminder_talk_names_consultation FROM conversations')).one()
        assert row == ('metawiki', 0)
        # The migrated schema enforces its own constraints, not only the models'.
        conn.execute(sa.text("INSERT INTO reminders (id, conversation_id, reminder_type, "
                             "send_day, created_at) VALUES (1, 1, 'results', '2026-11-02', "
                             "'2026-11-01')"))
        for bad in ("'delivered', NULL, NULL", "'failed', NULL, NULL", "'sent', NULL, 'x'",
                    "'failed', 'unknown', NULL"):
            with pytest.raises(sa.exc.IntegrityError):
                with conn.begin_nested():
                    conn.execute(sa.text(
                        "INSERT INTO reminder_deliveries (reminder_id, channel, status, reason, "
                        f"error_code) VALUES (1, 'email', {bad})"))
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(sa.text("INSERT INTO reminders (conversation_id, reminder_type, "
                                     "send_day, created_at) VALUES (1, 'results', "
                                     "'2026-11-02', '2026-11-01')"))
        migration.downgrade()
        inspector = sa.inspect(conn)
        assert set(inspector.get_table_names()) == {'conversations', 'participants',
                                                    'participations'}
        assert {c['name'] for c in inspector.get_columns('conversations')} == {'id', 'title'}
        assert conn.execute(sa.text('SELECT title FROM conversations')).scalar() == 'Old'


def test_the_migration_keeps_the_same_closed_lists_as_the_models():
    migration = _migration()
    assert migration._STATUSES == db_module.REMINDER_DELIVERY_STATUSES
    assert migration._REASONS == db_module.REMINDER_FAILURE_REASONS
