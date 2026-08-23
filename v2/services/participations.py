"""Participant join command shared by HTML and JSON adapters."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from db import Conversation, Participant, Participation, db

PSEUDONYM_RE = re.compile(r'^[a-z]{2,20}-[a-z]{2,20}$')


class InvalidPseudonym(ValueError):
    """The requested pseudonym does not match the public contract."""


class PseudonymUnavailable(RuntimeError):
    """Another participant already owns the requested pseudonym."""


class EligibilityDenied(RuntimeError):
    """The configured eligibility policy denied or could not verify the join."""

    def __init__(self, status: str, detail: dict):
        super().__init__(status)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class JoinResult:
    participation: Participation
    created: bool


def join_conversation(
    *,
    conversation: Conversation,
    participant: Participant,
    pseudonym: str,
    notify_email: bool,
    notify_talk_page: bool,
    emailable: bool,
    check_eligibility: Callable[[Conversation, Participant], tuple[bool, str, dict]],
) -> JoinResult:
    """Create one participation, returning the existing row on safe replay.

    The participant/conversation unique constraint is the idempotency boundary.
    Pseudonyms remain globally unique and therefore produce a distinct conflict.
    """
    existing = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conversation.id,
    ).first()
    if existing is not None:
        return JoinResult(participation=existing, created=False)

    pseudonym = pseudonym.strip()
    if PSEUDONYM_RE.fullmatch(pseudonym) is None:
        raise InvalidPseudonym(pseudonym)

    allowed, eligibility_status, eligibility_detail = check_eligibility(
        conversation, participant,
    )
    if not allowed:
        raise EligibilityDenied(eligibility_status, eligibility_detail)

    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym=pseudonym,
        notify_email=bool(notify_email and emailable),
        notify_talk_page=bool(notify_talk_page),
        eligibility_status=eligibility_status,
        eligibility_checked_at=(
            datetime.now(timezone.utc)
            if eligibility_status != 'not_required' else None
        ),
        eligibility_detail=eligibility_detail or None,
    )
    db.session.add(participation)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        existing = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conversation.id,
        ).first()
        if existing is not None:
            return JoinResult(participation=existing, created=False)
        raise PseudonymUnavailable(pseudonym) from exc
    return JoinResult(participation=participation, created=True)
