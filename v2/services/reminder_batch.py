"""The daily reminder batch (#577): who gets what today, recorded, in dry-run.

``run_batch`` handles one day. For each reminder due that day it records one
delivery per recipient and channel, then hands each person at most one message
per channel: everything due for them that day is combined into it, and the other
rows are marked ``combined``. Wiki-mail stops at the daily cap, least recently
mailed first; the rest are ``not_sent_limit`` and are not retried.

The sender is passed in. In this version it is a dry run: it records what it
would send and calls no wiki. Each delivery is claimed before it is handled, so
running the batch twice never handles one twice.

Nothing here logs or returns a username or any message text.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Protocol

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from db import Conversation, Participation, Reminder, ReminderDelivery, REMINDER_CHANNELS, db
from services import reminder_wikis
from services.reminders import is_expired, recipients

RETENTION_AFTER_LAST_MESSAGE = timedelta(days=14)
_DONE_EMAIL = ('sent', 'dry_run')


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
    reminders: int = 0
    waiting_for_trigger: int = 0           # due on a wiki where the bot is not approved
    counts: Counter = field(default_factory=Counter)   # (channel, status) -> rows
    blocked_wikis: set = field(default_factory=set)
    unlinked: int = 0


class ReminderNotFound(LookupError):
    pass


def run_batch(
    day: date, *, now: datetime, active_phases: Callable[[Conversation], set[str]],
    sender: Sender, email_cap: int, paused: bool = False,
    approved: dict[str, str] | None = None, reminder_id: int | None = None,
) -> BatchResult:
    """Handle one day's reminders.

    The scheduled run (``reminder_id`` empty) handles every reminder due on
    ``day`` whose consultation's wiki is approved for automatic sends; the
    others wait for a super admin. A super admin's trigger (``reminder_id``)
    handles that one reminder now, on any wiki the bot knows.
    """
    result = BatchResult()
    if paused:
        result.paused = True
        return result

    due = _due_reminders(day, approved, reminder_id, result)
    result.reminders = len(due)
    for reminder in due:
        _record_deliveries(reminder, active_phases(reminder.conversation))

    _hand_out(due, day=day, now=now, sender=sender, email_cap=email_cap, result=result)
    for reminder in due:
        for status, channel, count in (
            db.session.query(ReminderDelivery.status, ReminderDelivery.channel, sa.func.count())
            .filter_by(reminder_id=reminder.id)
            .group_by(ReminderDelivery.status, ReminderDelivery.channel)
        ):
            result.counts[(channel, status)] += count
    result.unlinked = unlink_ended(now)
    return result


def _due_reminders(day, approved, reminder_id, result) -> list[Reminder]:
    if reminder_id is not None:
        reminder = db.session.get(Reminder, reminder_id)
        if reminder is None:
            raise ReminderNotFound(reminder_id)
        return [reminder]
    due = []
    for reminder in Reminder.query.filter_by(send_day=day).order_by(Reminder.id):
        if reminder_wikis.is_approved(reminder.conversation.reminder_wiki, approved):
            due.append(reminder)
        else:
            result.waiting_for_trigger += 1
    return due


def _record_deliveries(reminder: Reminder, phases: set[str]) -> None:
    """One row per recipient and channel; an expired reminder is recorded as such."""
    expired = is_expired(reminder.reminder_type, reminder.phase_key, phases)
    existing = {
        (row.participation_id, row.channel)
        for row in ReminderDelivery.query.filter_by(reminder_id=reminder.id)
    }
    for channel in REMINDER_CHANNELS:
        for participation in recipients(reminder.conversation, channel):
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
    db.session.commit()


def _claim(row: ReminderDelivery, now: datetime) -> bool:
    claimed = (
        ReminderDelivery.query
        .filter_by(id=row.id, status='pending', claimed_at=None)
        .update({'claimed_at': now}, synchronize_session=False)
    )
    db.session.commit()
    return claimed == 1


def _hand_out(due, *, day, now, sender, email_cap, result) -> None:
    reminder_ids = [r.id for r in due]
    if not reminder_ids:
        return
    pending = (
        ReminderDelivery.query
        .filter(ReminderDelivery.reminder_id.in_(reminder_ids),
                ReminderDelivery.status == 'pending',
                ReminderDelivery.claimed_at.is_(None))
        .order_by(ReminderDelivery.reminder_id, ReminderDelivery.id)
        .all()
    )
    groups: dict[tuple, list[ReminderDelivery]] = defaultdict(list)
    for row in pending:
        if not _claim(row, now):
            continue
        wiki = row.reminder.conversation.reminder_wiki
        person = row.participation.participant_id
        # Wiki-mail reaches one global inbox, so one mail combines every wiki;
        # a talk page belongs to one wiki, so talk notes combine per wiki.
        key = (row.channel, person) if row.channel == 'email' else (row.channel, person, wiki)
        groups[key].append(row)

    email_groups = [g for k, g in groups.items() if k[0] == 'email']
    allowed = set(map(id, _within_cap(email_groups, day, email_cap)))

    for key, rows in groups.items():
        primary, rest = rows[0], rows[1:]
        wiki = primary.reminder.conversation.reminder_wiki
        if key[0] == 'email' and id(rows) not in allowed:
            _finish(rows, Outcome('not_sent_limit'), now)
            continue
        if (key[0], wiki) in result.blocked_wikis:
            _finish(rows, Outcome('failed', reason='blocked'), now)
            continue
        outcome = sender.send(channel=primary.channel, wiki=wiki,
                              participation=primary.participation,
                              reminders=[row.reminder for row in rows])
        if outcome.status == 'failed' and outcome.reason == 'blocked':
            # The bot itself is blocked there: stop that wiki's batch for this channel.
            result.blocked_wikis.add((key[0], wiki))
        _finish([primary], outcome, now)
        if rest:
            combined = outcome if outcome.status == 'failed' else Outcome('combined')
            _finish(rest, combined, now)
    db.session.commit()


def _within_cap(email_groups, day, cap) -> list[list[ReminderDelivery]]:
    """The groups that fit under today's wiki-mail cap, least recently mailed first."""
    start = datetime.combine(day, datetime.min.time())
    used = (
        ReminderDelivery.query
        .filter(ReminderDelivery.channel == 'email',
                ReminderDelivery.status.in_(_DONE_EMAIL),
                ReminderDelivery.attempted_at >= start,
                ReminderDelivery.attempted_at < start + timedelta(days=1))
        .count()
    )
    room = max(cap - used, 0)
    people = [rows[0].participation.participant_id for rows in email_groups]
    last_sent = dict(
        db.session.query(Participation.participant_id, sa.func.max(ReminderDelivery.attempted_at))
        .join(ReminderDelivery, ReminderDelivery.participation_id == Participation.id)
        .filter(Participation.participant_id.in_(people),
                ReminderDelivery.channel == 'email', ReminderDelivery.status == 'sent')
        .group_by(Participation.participant_id)
        .all()
    ) if people else {}
    ordered = sorted(
        email_groups,
        key=lambda rows: (last_sent.get(rows[0].participation.participant_id) is not None,
                          last_sent.get(rows[0].participation.participant_id) or datetime.min,
                          rows[0].participation.participant_id),
    )
    return ordered[:room]


def _finish(rows, outcome: Outcome, now: datetime) -> None:
    for row in rows:
        row.status = outcome.status
        row.reason = outcome.reason
        row.error_code = outcome.error_code
        row.sent_via = outcome.sent_via
        row.attempted_at = now


def unlink_ended(now: datetime) -> int:
    """Unlink deliveries from their person once retention allows.

    A consultation's rows are unlinked once it has ended (archived or closed)
    and two weeks have passed since its last message, whichever is later. The
    rows stay, so the totals do.
    """
    unlinked = 0
    ended = Conversation.query.filter(
        sa.or_(Conversation.closed_at.isnot(None), Conversation.active.is_(False)))
    for conversation in ended:
        rows = (
            ReminderDelivery.query
            .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
            .filter(Reminder.conversation_id == conversation.id,
                    ReminderDelivery.participation_id.isnot(None))
        )
        last = rows.with_entities(sa.func.max(ReminderDelivery.attempted_at)).scalar()
        if last is not None and last > now - RETENTION_AFTER_LAST_MESSAGE:
            continue
        ids = [row.id for row in rows.with_entities(ReminderDelivery.id)]
        if not ids:
            continue
        unlinked += (
            ReminderDelivery.query.filter(ReminderDelivery.id.in_(ids))
            .update({'participation_id': None, 'claimed_at': None, 'attempted_at': None},
                    synchronize_session=False)
        )
    db.session.commit()
    return unlinked
