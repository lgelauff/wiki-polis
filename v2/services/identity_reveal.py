"""Identity-reveal timeline and irreversible participant command."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from db import Conversation, Participation, db

REVEAL_COOLDOWN_DAYS = 30
REVEAL_WINDOW_DAYS = 30


class RevealUnavailable(RuntimeError):
    """The requested reveal cannot be performed in the current timeline state."""

    def __init__(self, state: str):
        super().__init__(state)
        self.state = state


@dataclass(frozen=True)
class RevealResult:
    participation: Participation
    created: bool


def build_reveal_context(
    conversation: Conversation,
    participation: Participation | None,
    *,
    now: datetime | None = None,
) -> dict | None:
    """Return the canonical reveal timeline for a closed conversation."""
    if not conversation.closed_at:
        return None
    closed = (
        conversation.closed_at
        if conversation.closed_at.tzinfo
        else conversation.closed_at.replace(tzinfo=timezone.utc)
    )
    opens_at = closed + timedelta(days=REVEAL_COOLDOWN_DAYS)
    closes_at = closed + timedelta(
        days=REVEAL_COOLDOWN_DAYS + REVEAL_WINDOW_DAYS,
    )
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = current - closed
    if participation and participation.public_username:
        state = 'revealed'
    elif age >= timedelta(days=REVEAL_COOLDOWN_DAYS + REVEAL_WINDOW_DAYS):
        state = 'expired'
    elif age >= timedelta(days=REVEAL_COOLDOWN_DAYS):
        state = 'open'
    else:
        state = 'pending'

    target = opens_at if state == 'pending' else closes_at if state == 'open' else None
    days_left = 0
    if target is not None:
        delta = target - current
        days_left = max(
            0,
            delta.days + (1 if (delta.seconds or delta.microseconds) else 0),
        )
    return {
        'closed_at': closed,
        'opens_at': opens_at,
        'closes_at': closes_at,
        'state': state,
        'days_left': days_left,
        'countdown_target_iso': target.isoformat() if target else None,
        'cooldown_days': REVEAL_COOLDOWN_DAYS,
        'window_days': REVEAL_WINDOW_DAYS,
    }


def reveal_identity(
    *,
    conversation: Conversation,
    participation: Participation,
    wikimedia_username: str,
    now: datetime | None = None,
) -> RevealResult:
    """Permanently publish the participant's identity, safely replaying success."""
    locked = (
        Participation.query
        .filter_by(id=participation.id)
        .with_for_update()
        .one()
    )
    if locked.public_username is not None:
        return RevealResult(participation=locked, created=False)

    timeline = build_reveal_context(conversation, locked, now=now)
    state = timeline['state'] if timeline else 'not_closed'
    if state != 'open':
        raise RevealUnavailable(state)

    locked.public_username = wikimedia_username
    locked.revealed_at = now or datetime.now(timezone.utc)
    db.session.commit()
    return RevealResult(participation=locked, created=True)
