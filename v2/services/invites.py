"""Transactional invitation commands shared by HTML and API adapters."""

from dataclasses import dataclass
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import ConversationInvite


@dataclass(frozen=True)
class InviteBatchResult:
    added: int
    already_present: int
    concurrent_conflicts: int
    duplicate_inputs: int


class InviteBatchSaveError(RuntimeError):
    """The batch transaction failed and no new invitation was persisted."""


def add_conversation_invites(session, *, conversation_id: int,
                             usernames: Iterable[str]) -> InviteBatchResult:
    """Add each missing username without losing unrelated rows to a race.

    Each insert gets a savepoint. A concurrent unique-key winner rolls back only
    that username; an unrelated database failure rolls back the whole command.
    """
    submitted = list(usernames)
    candidates = list(dict.fromkeys(submitted))
    duplicate_inputs = len(submitted) - len(candidates)

    try:
        existing = set(session.scalars(
            select(ConversationInvite.mw_username).where(
                ConversationInvite.conversation_id == conversation_id)
        ))
        pending = [username for username in candidates if username not in existing]
        added = 0
        concurrent_conflicts = 0

        for username in pending:
            try:
                with session.begin_nested():
                    session.add(ConversationInvite(
                        conversation_id=conversation_id,
                        mw_username=username,
                    ))
                    session.flush()
            except IntegrityError:
                concurrent_conflicts += 1
            else:
                added += 1

        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise InviteBatchSaveError('invite batch transaction failed') from exc

    return InviteBatchResult(
        added=added,
        already_present=len(candidates) - len(pending),
        concurrent_conflicts=concurrent_conflicts,
        duplicate_inputs=duplicate_inputs,
    )
