"""Reminder rules (#577): who may send, who receives, and when a reminder expires.

Nothing here sends. The daily batch (a later PR) uses these rules to decide what
to record; this module only reads the database.
"""

from collections.abc import Iterable

from db import (
    ACCOUNT_KIND_WIKIMEDIA, ConversationBan, Participant, Participation, REMINDER_CHANNELS, db,
)

PHASE_OPENED = 'phase_opened'
PHASE_CLOSING = 'phase_closing'
RESULTS = 'results'
# "Unanswered items" follows in its own PR: it needs each person's unvoted count from Polis.
REMINDER_TYPES = (PHASE_OPENED, PHASE_CLOSING, RESULTS)

_CHANNEL_FLAG = {'email': Participation.notify_email, 'talk': Participation.notify_talk_page}


def can_send_reminders(participant: Participant | None, conversation,
                       *, admin_usernames: Iterable[str] = ()) -> bool:
    """Super admins only, hardcoded. Organizers come later as a code change."""
    if participant is None:
        return False
    if participant.is_global_admin:
        return True
    return bool(participant.mw_username) and participant.mw_username in set(admin_usernames)


def recipients(conversation, channel: str) -> list[Participation]:
    """Joined participants with a Wikimedia account who ticked this channel.

    Access-code accounts, demo accounts and people with an active ban in this
    consultation are never recipients. People who were invited but never joined
    have no participation, so they are not here either.
    """
    if channel not in REMINDER_CHANNELS:
        raise ValueError(f'unknown channel: {channel}')
    banned = db.session.query(ConversationBan.participant_id).filter(
        ConversationBan.conversation_id == conversation.id,
        ConversationBan.lifted_at.is_(None),
    )
    return (
        Participation.query
        .join(Participant, Participant.id == Participation.participant_id)
        .filter(
            Participation.conversation_id == conversation.id,
            _CHANNEL_FLAG[channel].is_(True),
            Participant.account_kind == ACCOUNT_KIND_WIKIMEDIA,
            Participant.mw_username.isnot(None),
            Participant.is_demo.is_(False),
            Participation.participant_id.notin_(banned),
        )
        .order_by(Participation.id)
        .all()
    )


def is_expired(reminder_type: str, phase_key: str | None, active_phases: set[str]) -> bool:
    """True when the reminder's moment has passed by its send day.

    ``active_phases`` is the consultation's state on the send day: the phase keys
    that are on, plus ``closed`` once it is permanently closed.

    - Phase opened, phase closing soon: expired once that phase is no longer on
      (it closed, or a later phase opened) or the consultation is closed.
    - Final message (results): only goes out once the consultation is closed;
      before that it is dropped as expired, never held for later.
    """
    if reminder_type in (PHASE_OPENED, PHASE_CLOSING):
        if not phase_key:
            raise ValueError(f'{reminder_type} needs a phase')
        return 'closed' in active_phases or phase_key not in active_phases
    if reminder_type == RESULTS:
        return 'closed' not in active_phases
    raise ValueError(f'unknown reminder type: {reminder_type}')
