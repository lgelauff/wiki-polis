"""A super admin's staff-only reminder run (#576, step 1: dry run).

One reminder for one consultation, recorded now and handed out at once by the
daily batch, to the consultation's staff only: organizers, moderators and super
admins who joined and ticked a channel. Every rule of the batch applies (the
daily wiki-mail cap, one message per person per day and channel, expiry). The
sender is the dry run, so nothing reaches a wiki.

The per-person result is read back from the delivery rows the batch stores;
nothing else is stored, and no message text is kept.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from sqlalchemy.exc import IntegrityError

from db import Participant, Participation, Reminder, ReminderDelivery, REMINDER_CHANNELS, db
from services import reminder_wikis
from services.reminder_batch import DryRunSender, run_batch
from services.reminders import RESULTS, REMINDER_TYPES, recipients, staff_participant_ids
from services.wiki_bot import WIKI_HOSTS


class ReminderExists(RuntimeError):
    """This consultation already has this reminder for today (one per moment)."""


class RemindersPaused(RuntimeError):
    pass


class UnknownWiki(ValueError):
    """The consultation's reminder wiki is not one the bot knows."""


@dataclass(frozen=True)
class StaffRun:
    reminder_id: int
    rows: list[dict]


def staff_state(conversation, *, admin_usernames: Iterable[str]) -> dict:
    """What the dry run would reach: staff recipients per channel, and the wiki."""
    staff = staff_participant_ids(conversation, admin_usernames=admin_usernames)
    wiki = conversation.reminder_wiki
    return {
        'wiki': wiki,
        'wikiHost': WIKI_HOSTS.get(wiki),
        'automatedSendApproved': reminder_wikis.is_approved(wiki),
        'reminderTypes': list(REMINDER_TYPES),
        'counts': {
            channel: sum(1 for person in recipients(conversation, channel)
                         if person.participant_id in staff)
            for channel in REMINDER_CHANNELS
        },
    }


def run_staff_dry_run(
    conversation, reminder_type: str, *, phase_key: str, now: datetime,
    triggered_by: Participant, admin_usernames: Iterable[str],
    active_phases: Callable, email_cap: int, paused: bool,
) -> StaffRun:
    """Record the reminder and run the batch for it, staff only, in dry run."""
    if reminder_type not in REMINDER_TYPES:
        raise ValueError(reminder_type)
    if paused:
        raise RemindersPaused()
    if not reminder_wikis.is_known_wiki(conversation.reminder_wiki):
        raise UnknownWiki(conversation.reminder_wiki)
    phase = '' if reminder_type == RESULTS else phase_key
    moment = Reminder.query.filter_by(
        conversation_id=conversation.id, reminder_type=reminder_type, phase_key=phase,
        send_day=now.date()).first()
    if moment is not None:
        raise ReminderExists()
    reminder = Reminder(conversation_id=conversation.id, reminder_type=reminder_type,
                        phase_key=phase, send_day=now.date(), created_by_id=triggered_by.id)
    db.session.add(reminder)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ReminderExists() from None
    staff = staff_participant_ids(conversation, admin_usernames=admin_usernames)
    try:
        run_batch(now.date(), now=now, active_phases=active_phases, sender=DryRunSender(),
                  email_cap=email_cap, reminder_id=reminder.id,
                  triggered_by_id=triggered_by.id,
                  audience=lambda conv: staff if conv.id == conversation.id else set())
    except Exception:
        # A reminder the batch never recorded must not stay behind: a later scheduled
        # run would record it for every participant, not for staff.
        db.session.rollback()
        unrecorded = db.session.get(Reminder, reminder.id)
        if unrecorded is not None and unrecorded.recorded_at is None:
            db.session.delete(unrecorded)
            db.session.commit()
        raise
    return StaffRun(reminder_id=reminder.id, rows=staff_run_rows(reminder.id))


def staff_run_rows(reminder_id: int) -> list[dict]:
    """Per person and channel: the username and what happened."""
    rows = (
        db.session.query(Participant.mw_username, ReminderDelivery)
        .join(Participation, Participation.id == ReminderDelivery.participation_id)
        .join(Participant, Participant.id == Participation.participant_id)
        .filter(ReminderDelivery.reminder_id == reminder_id)
        .order_by(Participant.mw_username, ReminderDelivery.channel)
        .all()
    )
    return [{
        'username': username, 'channel': row.channel, 'status': row.status,
        'reason': row.reason, 'errorCode': row.error_code,
    } for username, row in rows]
