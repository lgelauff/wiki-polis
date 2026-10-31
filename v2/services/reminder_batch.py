"""The daily reminder batch (#577): who gets what today, recorded, in dry-run.

``run_batch`` handles one day. For each reminder due that day it records one
delivery per recipient and channel, then hands each person at most one message
per channel and day: everything due for them is combined into it, and the other
rows are marked ``combined``. Wiki-mail stops at the daily cap, least recently
mailed first; the rest are ``not_sent_limit`` and are not retried.

Safety, in order of the steps:

- One run at a time (a database lock on MariaDB); a second run stops at once.
- A reminder's deliveries are recorded once (``recorded_at``).
- Each person's message is claimed, sent and saved on its own, so a crash leaves
  at most one message unsettled. A claim left unsettled is later recorded as
  ``failed``/``outcome_unknown`` and never resent: it may have gone out.
- Just before sending, the person must still be a recipient (ticks, bans) and
  the reminder must not have expired.

The sender is passed in. In this version it is a dry run: it records what it
would send and calls no wiki. Nothing here logs or returns a username or any
message text.
"""

import logging
import random
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable, Protocol

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from db import (
    Conversation, Participation, Reminder, ReminderDelivery, REMINDER_CHANNELS,
    REMINDER_DELIVERY_STATUSES, REMINDER_FAILURE_REASONS, db,
)
from services import reminder_wikis
from services.reminders import is_expired, recipients

log = logging.getLogger(__name__)

RETENTION_AFTER_LAST_MESSAGE = timedelta(days=14)
STALE_CLAIM = timedelta(minutes=30)
MAX_EMAIL_CAP = 20            # Wikimedia's limit for an unflagged bot
_DELIVERED = ('sent', 'dry_run')
_LOCK_NAME = 'proto-reminder-batch'


@dataclass(frozen=True)
class Outcome:
    status: str                    # sent | dry_run | failed | skipped_optout
    reason: str | None = None
    error_code: str | None = None
    sent_via: str | None = None


class Sender(Protocol):
    def send(self, *, channel: str, wiki: str, participation: Participation,
             reminders: list[Reminder]) -> Outcome: ...


class DryRunSender:
    """Records the send it would make; no network call."""

    def send(self, *, channel, wiki, participation, reminders):
        return Outcome('dry_run', sent_via=wiki)


@dataclass
class BatchResult:
    paused: bool = False
    day: date | None = None
    due: list = field(default_factory=list)              # reminder ids handled in this run
    waiting_for_trigger: list = field(default_factory=list)   # ids on a wiki not approved
    unknown_wiki: list = field(default_factory=list)     # ids on a wiki the bot doesn't know
    missed: list = field(default_factory=list)           # ids whose day passed unrecorded
    this_run: Counter = field(default_factory=Counter)   # (channel, status) -> rows settled now
    totals: Counter = field(default_factory=Counter)     # (channel, status) -> all rows so far
    blocked_wikis: set = field(default_factory=set)
    stale_claims: int = 0
    unlinked: int = 0


class ReminderNotFound(LookupError):
    pass


class UnknownReminderWiki(ValueError):
    """The consultation's reminder wiki is not one the bot knows."""


class TriggerNeedsSuperAdmin(PermissionError):
    """A super admin's trigger must say which super admin triggers it."""


class BatchBusy(RuntimeError):
    """Another reminder run holds the lock."""


def email_cap_from(value) -> int:
    """The configured daily wiki-mail cap, kept within 0..20; a bad value means 5."""
    try:
        cap = int(str(value).strip()) if str(value).strip() else 5
    except ValueError:
        log.error('REMINDERS_EMAIL_DAILY_CAP is not a whole number; using 5')
        return 5
    if cap < 0:
        log.error('REMINDERS_EMAIL_DAILY_CAP is negative; using 5')
        return 5
    return min(cap, MAX_EMAIL_CAP)


@contextmanager
def single_flight():
    """One reminder run at a time. MariaDB has a named lock; SQLite (tests, local) has
    one process anyway."""
    bind = db.session.get_bind()
    if bind.dialect.name not in ('mysql', 'mariadb'):
        yield
        return
    got = db.session.execute(sa.text('SELECT GET_LOCK(:n, 0)'), {'n': _LOCK_NAME}).scalar()
    if got != 1:
        raise BatchBusy()
    try:
        yield
    finally:
        db.session.execute(sa.text('SELECT RELEASE_LOCK(:n)'), {'n': _LOCK_NAME})


def run_batch(
    day: date, *, now: datetime, active_phases: Callable[[Conversation], set[str]],
    sender: Sender, email_cap: int, paused: bool | Callable[[], bool] = False,
    approved: dict[str, str] | None = None, reminder_id: int | None = None,
    triggered_by_id: int | None = None,
) -> BatchResult:
    """Handle one day's reminders.

    The scheduled run (``reminder_id`` empty) handles every reminder due on
    ``day`` whose consultation's wiki is approved for automatic sends; the
    others wait for a super admin. A reminder on an approved wiki whose day
    passed unrecorded (the job did not run, or reminders were paused) is
    recorded as ``skipped_expired``, as #577 says.

    A super admin's trigger (``reminder_id`` and ``triggered_by_id``) handles
    that one reminder now, on any wiki the bot knows, and records who
    triggered it first and when.

    ``paused`` may be a callable; it is checked before the run and between
    messages, so pausing mid-run stops the rest.
    """
    is_paused = paused if callable(paused) else (lambda: paused)
    result = BatchResult(day=day)
    if is_paused():
        result.paused = True
        return result
    if reminder_id is not None and triggered_by_id is None:
        raise TriggerNeedsSuperAdmin()

    with single_flight():
        result.stale_claims = _settle_stale_claims(now)
        due = _due_reminders(day, approved, reminder_id, result)
        if reminder_id is not None and due[0].triggered_at is None:
            due[0].triggered_at = now
            due[0].triggered_by_id = triggered_by_id
            db.session.commit()
        for reminder in due:
            if reminder.recorded_at is None:
                _record_deliveries(reminder, active_phases(reminder.conversation), now)
        if reminder_id is None:
            _record_missed(day, approved, now, result)

        _hand_out(due, now=now, sender=sender, email_cap=email_cap, result=result,
                  active_phases=active_phases, is_paused=is_paused)
        result.due = [r.id for r in due]
        for reminder in due:
            for status, channel, count in (
                db.session.query(ReminderDelivery.status, ReminderDelivery.channel,
                                 sa.func.count())
                .filter_by(reminder_id=reminder.id)
                .group_by(ReminderDelivery.status, ReminderDelivery.channel)
            ):
                result.totals[(channel, status)] += count
        result.unlinked = unlink_ended(now)
    return result


def _due_reminders(day, approved, reminder_id, result) -> list[Reminder]:
    if reminder_id is not None:
        reminder = db.session.get(Reminder, reminder_id)
        if reminder is None:
            raise ReminderNotFound(reminder_id)
        if not reminder_wikis.is_known_wiki(reminder.conversation.reminder_wiki):
            raise UnknownReminderWiki(reminder.conversation.reminder_wiki)
        return [reminder]
    due = []
    for reminder in Reminder.query.filter_by(send_day=day).order_by(Reminder.id):
        wiki = reminder.conversation.reminder_wiki
        if not reminder_wikis.is_known_wiki(wiki):
            result.unknown_wiki.append(reminder.id)
        elif reminder_wikis.is_approved(wiki, approved):
            due.append(reminder)
        else:
            result.waiting_for_trigger.append(reminder.id)
    return due


def _record_missed(day, approved, now, result) -> None:
    """Approved-wiki reminders whose day passed unrecorded are dropped as expired.

    Reminders on a wiki that is not approved keep waiting for a super admin;
    on an unknown wiki they are reported on every run.
    """
    for reminder in (Reminder.query
                     .filter(Reminder.send_day < day, Reminder.recorded_at.is_(None))
                     .order_by(Reminder.id)):
        wiki = reminder.conversation.reminder_wiki
        if not reminder_wikis.is_known_wiki(wiki):
            result.unknown_wiki.append(reminder.id)
        elif reminder_wikis.is_approved(wiki, approved):
            _record_deliveries(reminder, set(), now, expired=True)
            result.missed.append(reminder.id)
        else:
            result.waiting_for_trigger.append(reminder.id)


def _record_deliveries(reminder: Reminder, phases: set[str], now: datetime,
                       *, expired: bool | None = None) -> None:
    """One row per recipient and channel; an expired reminder is recorded as such.

    Recipients are inserted in random order, so a row's id says nothing about
    who it was for once it is unlinked.
    """
    if expired is None:
        expired = is_expired(reminder.reminder_type, reminder.phase_key, phases)
    existing = {
        (row.participation_id, row.channel)
        for row in ReminderDelivery.query.filter_by(reminder_id=reminder.id)
    }
    shuffle = random.SystemRandom().shuffle
    for channel in REMINDER_CHANNELS:
        people = recipients(reminder.conversation, channel)
        shuffle(people)
        for participation in people:
            if (participation.id, channel) in existing:
                continue
            row = ReminderDelivery(
                reminder_id=reminder.id, participation_id=participation.id, channel=channel,
                status='skipped_expired' if expired else 'pending',
            )
            try:
                with db.session.begin_nested():
                    db.session.add(row)
            except IntegrityError:
                pass   # another run recorded it first
    reminder.recorded_at = now
    db.session.commit()


def _settle_stale_claims(now: datetime) -> int:
    """A claim older than STALE_CLAIM with no outcome: the run died mid-send.
    It may have gone out, so it is recorded as outcome_unknown and never resent."""
    settled = (
        ReminderDelivery.query
        .filter(ReminderDelivery.status == 'pending',
                ReminderDelivery.claimed_at.isnot(None),
                ReminderDelivery.claimed_at < now - STALE_CLAIM,
                ReminderDelivery.attempted_at.is_(None))
        .update({'status': 'failed', 'reason': 'outcome_unknown', 'attempted_at': now},
                synchronize_session=False)
    )
    db.session.commit()
    if settled:
        log.error('reminders: %s claimed deliveries had no outcome; recorded as outcome_unknown',
                  settled)
    return settled


def _claim(rows, now: datetime) -> list[ReminderDelivery]:
    """Claim the rows that are still free; returns the ones this run now holds."""
    held = []
    for row in rows:
        claimed = (
            ReminderDelivery.query
            .filter_by(id=row.id, status='pending', claimed_at=None)
            .update({'claimed_at': now}, synchronize_session=False)
        )
        if claimed == 1:
            held.append(row)
    db.session.commit()
    for row in held:
        db.session.refresh(row)
    return held


def _valid(outcome: Outcome) -> Outcome:
    """A sender's outcome must fit the delivery table; anything else is unknown."""
    ok = (outcome.status in REMINDER_DELIVERY_STATUSES
          and outcome.status not in ('pending', 'combined')
          and (outcome.status == 'failed') == (outcome.reason in REMINDER_FAILURE_REASONS)
          and (outcome.error_code is None or outcome.status == 'failed'))
    if ok:
        return outcome
    log.error('reminders: sender returned an outcome the log cannot hold: %s/%s',
              outcome.status, outcome.reason)
    return Outcome('failed', reason='outcome_unknown')


def _hand_out(due, *, now, sender, email_cap, result, active_phases, is_paused) -> None:
    reminder_ids = [r.id for r in due]
    if not reminder_ids:
        return
    pending = (
        ReminderDelivery.query
        .filter(ReminderDelivery.reminder_id.in_(reminder_ids),
                ReminderDelivery.status == 'pending',
                ReminderDelivery.claimed_at.is_(None),
                ReminderDelivery.participation_id.isnot(None))
        .order_by(ReminderDelivery.reminder_id, ReminderDelivery.id)
        .all()
    )
    # Still a recipient, and the reminder still current, at the moment of sending.
    current = {}
    phases = {}
    for row in pending:
        conv = row.reminder.conversation
        if (conv.id, row.channel) not in current:
            current[(conv.id, row.channel)] = {p.id for p in recipients(conv, row.channel)}
        if conv.id not in phases:
            phases[conv.id] = active_phases(conv)

    groups: dict[tuple, list[ReminderDelivery]] = defaultdict(list)
    for row in pending:
        wiki = row.reminder.conversation.reminder_wiki
        person = row.participation.participant_id
        # Wiki-mail reaches one global inbox, so one mail combines every wiki;
        # a talk page belongs to one wiki, so talk notes combine per wiki.
        key = (row.channel, person) if row.channel == 'email' else (row.channel, person, wiki)
        groups[key].append(row)

    day_start = datetime.combine(now.date(), time.min)
    room = max(email_cap - _delivered_mail_today(day_start), 0)
    order = sorted(groups, key=lambda k: (k[0] != 'email', _last_mailed_key(k, groups)))
    for key in order:
        if is_paused():
            log.warning('reminders paused mid-run; the rest stays for later')
            break
        rows = _claim(groups[key], now)
        if not rows:
            continue
        channel, person = key[0], key[1]
        live, gone = [], []
        for row in rows:
            conv = row.reminder.conversation
            if row.participation_id not in current[(conv.id, channel)]:
                gone.append((row, Outcome('skipped_optout')))
            elif is_expired(row.reminder.reminder_type, row.reminder.phase_key,
                            phases[conv.id]):
                gone.append((row, Outcome('skipped_expired')))
            else:
                live.append(row)
        for row, outcome in gone:
            _finish([row], outcome, now, result)
        if not live:
            db.session.commit()
            continue
        wiki = live[0].reminder.conversation.reminder_wiki
        if (channel, wiki) in result.blocked_wikis:
            _finish(live, Outcome('failed', reason='blocked'), now, result)
        elif _already_messaged_today(person, channel, wiki, day_start, exclude=live):
            # One message per person per day and channel, across runs too.
            _finish(live, Outcome('not_sent_limit'), now, result)
        elif channel == 'email' and room <= 0:
            _finish(live, Outcome('not_sent_limit'), now, result)
        else:
            try:
                outcome = _valid(sender.send(channel=channel, wiki=wiki,
                                             participation=live[0].participation,
                                             reminders=[row.reminder for row in live]))
            except Exception:
                log.exception('reminders: the sender raised; recorded as outcome_unknown')
                outcome = Outcome('failed', reason='outcome_unknown')
            if outcome.status == 'failed' and outcome.reason == 'blocked':
                # The bot itself is blocked on the wiki that answered (a fallback mail
                # answers from Meta): stop that wiki's batch for this channel.
                result.blocked_wikis.add((channel, outcome.sent_via or wiki))
            if channel == 'email' and outcome.status in _DELIVERED:
                room -= 1
            _finish(live[:1], outcome, now, result)
            if live[1:]:
                rest = Outcome('combined') if outcome.status in _DELIVERED else outcome
                _finish(live[1:], rest, now, result)
        db.session.commit()


def _delivered_mail_today(day_start: datetime) -> int:
    return (
        ReminderDelivery.query
        .filter(ReminderDelivery.channel == 'email',
                ReminderDelivery.status.in_(_DELIVERED),
                ReminderDelivery.attempted_at >= day_start,
                ReminderDelivery.attempted_at < day_start + timedelta(days=1))
        .count()
    )


def _last_mailed_key(key, groups):
    """Least recently mailed first; never mailed before anyone mailed."""
    if key[0] != 'email':
        return (False, datetime.min, key[1])
    last = (
        db.session.query(sa.func.max(ReminderDelivery.attempted_at))
        .join(Participation, ReminderDelivery.participation_id == Participation.id)
        .filter(Participation.participant_id == key[1], ReminderDelivery.channel == 'email',
                ReminderDelivery.status == 'sent')
        .scalar()
    )
    return (last is not None, last or datetime.min, key[1])


def _already_messaged_today(person, channel, wiki, day_start, *, exclude) -> bool:
    query = (
        ReminderDelivery.query
        .join(Participation, ReminderDelivery.participation_id == Participation.id)
        .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
        .join(Conversation, Conversation.id == Reminder.conversation_id)
        .filter(Participation.participant_id == person,
                ReminderDelivery.channel == channel,
                ReminderDelivery.status.in_(_DELIVERED),
                ReminderDelivery.attempted_at >= day_start,
                ReminderDelivery.id.notin_([row.id for row in exclude]))
    )
    if channel == 'talk':
        query = query.filter(Conversation.reminder_wiki == wiki)
    return db.session.query(query.exists()).scalar()


def _finish(rows, outcome: Outcome, now: datetime, result: BatchResult) -> None:
    for row in rows:
        row.status = outcome.status
        row.reason = outcome.reason
        row.error_code = outcome.error_code
        row.sent_via = outcome.sent_via
        row.attempted_at = now
        result.this_run[(row.channel, outcome.status)] += 1


def unlink_ended(now: datetime) -> int:
    """Unlink deliveries from their person once retention allows.

    A consultation's rows are unlinked once it has ended (archived or closed)
    and two weeks have passed since its last message was sent, whichever is
    later. Rows still waiting are settled first (``skipped_expired``, or
    ``outcome_unknown`` if claimed). Then the person, the timestamps, the
    wiki's error code and the sending wiki are cleared. The rows stay, with
    channel, status and reason, so the totals do.
    """
    unlinked = 0
    linked = sa.exists().where(
        Reminder.conversation_id == Conversation.id,
        ReminderDelivery.reminder_id == Reminder.id,
        ReminderDelivery.participation_id.isnot(None),
    )
    ended = Conversation.query.filter(
        sa.or_(Conversation.closed_at.isnot(None), Conversation.active.is_(False)), linked)
    for conversation in ended:
        rows = (
            ReminderDelivery.query
            .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
            .filter(Reminder.conversation_id == conversation.id,
                    ReminderDelivery.participation_id.isnot(None))
        )
        last = (rows.filter(ReminderDelivery.status.in_(_DELIVERED))
                .with_entities(sa.func.max(ReminderDelivery.attempted_at)).scalar())
        if last is not None and last > now - RETENTION_AFTER_LAST_MESSAGE:
            continue
        ids = [row.id for row in rows.with_entities(ReminderDelivery.id)]
        if not ids:
            continue
        waiting = ReminderDelivery.query.filter(ReminderDelivery.id.in_(ids),
                                                ReminderDelivery.status == 'pending')
        waiting.filter(ReminderDelivery.claimed_at.isnot(None)).update(
            {'status': 'failed', 'reason': 'outcome_unknown'}, synchronize_session=False)
        waiting.update({'status': 'skipped_expired'}, synchronize_session=False)
        unlinked += (
            ReminderDelivery.query.filter(ReminderDelivery.id.in_(ids))
            .update({'participation_id': None, 'claimed_at': None, 'attempted_at': None,
                     'error_code': None, 'sent_via': None},
                    synchronize_session=False)
        )
    db.session.commit()
    return unlinked
