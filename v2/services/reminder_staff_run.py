"""A super admin's staff-only reminder run (#576, step 1: dry run).

One reminder for one consultation, recorded now and handed out at once by the
daily batch, to the consultation's staff only: organizers, moderators and super
admins who joined and ticked a channel. Every rule of the batch applies (the
daily wiki-mail cap, one message per person per day and channel, expiry). The
sender is the dry run, so nothing reaches a wiki.

The per-person result is read back from the delivery rows the batch stores;
nothing else is stored, and no message text is kept.

A dry run is an ordinary reminder moment (#576, to settle before step 2): it
takes the day's one-per-moment slot for its type and phase, and its ``dry_run``
rows count toward the daily wiki-mail cap and the one-message-per-day rule, as
every dry run of the batch does. So it can show "held back" because of another
consultation's run the same day.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from sqlalchemy.exc import IntegrityError

from db import Participant, Participation, Reminder, ReminderDelivery, REMINDER_CHANNELS, db
from services import reminder_wikis
from services.reminder_batch import BatchBusy, DryRunSender, record_reminder, run_batch
from services.reminders import (
    RESULTS, REMINDER_TYPES, is_expired, recipients, staff_participant_ids,
)
from services.wiki_bot import WIKI_HOSTS


class ReminderExists(RuntimeError):
    """This consultation already has this reminder for today (one per moment)."""


class RemindersPaused(RuntimeError):
    pass


class UnknownWiki(ValueError):
    """The consultation's reminder wiki is not one the bot knows."""


class NotDue(RuntimeError):
    """The message's moment has passed or not come (the batch would record it as expired)."""


class NoRecipients(RuntimeError):
    """No staff member joined and ticked a channel, so the run would reach nobody."""


@dataclass(frozen=True)
class StaffRun:
    reminder_id: int
    rows: list[dict]


def staff_state(conversation, *, admin_usernames: Iterable[str], phase_key: str,
                active_phases: Callable) -> dict:
    """What the dry run would reach: staff recipients per channel, the wiki, and the
    message types that are due now (a type that would only be recorded as expired is
    left out)."""
    phases = active_phases(conversation)
    staff = staff_participant_ids(conversation, admin_usernames=admin_usernames)
    wiki = conversation.reminder_wiki
    return {
        'wiki': wiki,
        'wikiHost': WIKI_HOSTS.get(wiki),
        'automatedSendApproved': reminder_wikis.is_approved(wiki),
        'reminderTypes': [
            kind for kind in REMINDER_TYPES
            if not is_expired(kind, '' if kind == RESULTS else phase_key, phases)],
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
    """Record the reminder and run the batch for it, staff only, in dry run.

    The reminder and its staff deliveries are recorded in one commit, so no other
    run ever sees the reminder unrecorded; the batch then only hands them out.
    """
    if reminder_type not in REMINDER_TYPES:
        raise ValueError(reminder_type)
    if paused:
        raise RemindersPaused()
    if not reminder_wikis.is_known_wiki(conversation.reminder_wiki):
        raise UnknownWiki(conversation.reminder_wiki)
    phase = '' if reminder_type == RESULTS else phase_key
    phases = active_phases(conversation)
    if is_expired(reminder_type, phase, phases):
        raise NotDue()
    staff = staff_participant_ids(conversation, admin_usernames=admin_usernames)
    if not any(person.participant_id in staff
               for channel in REMINDER_CHANNELS for person in recipients(conversation, channel)):
        raise NoRecipients()
    moment = Reminder.query.filter_by(
        conversation_id=conversation.id, reminder_type=reminder_type, phase_key=phase,
        send_day=now.date()).first()
    if moment is not None:
        raise ReminderExists()

    def audience(conv):
        return staff if conv.id == conversation.id else set()

    reminder = Reminder(conversation_id=conversation.id, reminder_type=reminder_type,
                        phase_key=phase, send_day=now.date(), created_by_id=triggered_by.id)
    try:
        db.session.add(reminder)
        db.session.flush()
        record_reminder(reminder, phases, now, audience=audience)
    except IntegrityError:
        db.session.rollback()
        raise ReminderExists() from None
    try:
        run_batch(now.date(), now=now, active_phases=active_phases, sender=DryRunSender(),
                  email_cap=email_cap, reminder_id=reminder.id,
                  triggered_by_id=triggered_by.id, audience=audience)
    except BatchBusy:
        # The batch never started: nothing was handed out, so the reminder goes again
        # and the admin can retry once the other run has finished.
        db.session.rollback()
        ReminderDelivery.query.filter_by(reminder_id=reminder.id).delete(
            synchronize_session=False)
        Reminder.query.filter_by(id=reminder.id).delete(synchronize_session=False)
        db.session.commit()
        raise
    except BaseException:
        # Rows this run did not hand out are closed, so no later run hands them out
        # with another sender. A claimed row is left to the batch's own stale-claim rule.
        db.session.rollback()
        (ReminderDelivery.query
         .filter_by(reminder_id=reminder.id, status='pending', claimed_at=None)
         .update({'status': 'skipped_expired'}, synchronize_session=False))
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
