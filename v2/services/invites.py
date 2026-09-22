"""Transactional invitation commands shared by HTML and API adapters."""

from dataclasses import dataclass
from collections.abc import Iterable
from datetime import timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import Conversation, ConversationInvite, Participant


@dataclass(frozen=True)
class InviteBatchResult:
    added: int
    already_present: int
    concurrent_conflicts: int
    duplicate_inputs: int


class InviteBatchSaveError(RuntimeError):
    """The batch transaction failed and no new invitation was persisted."""


def _utc_iso(value) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_invitation_roster(
    *, conversation: Conversation, self_link: str, conversation_link: str,
) -> dict:
    rows = (
        ConversationInvite.query
        .filter_by(conversation_id=conversation.id)
        .order_by(ConversationInvite.mw_username)
        .all()
    )
    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
            'accessPolicy': conversation.access_policy,
        },
        'invitations': [{
            'id': row.id,
            'username': row.mw_username,
            'createdAt': _utc_iso(row.created_at),
        } for row in rows],
        'capabilities': {'manageInvitations': True},
        'links': {'self': self_link, 'conversation': conversation_link},
    }


class InvitationNotInConversation(LookupError):
    pass


def claim_username_invites(session, *, mw_user_id: int, mw_username: str) -> int:
    """Bind invitations made by username before this account's first login.

    The invite-only check matches the stable Wikimedia user id, so an invitation
    added for someone who had never logged in (``mw_user_id`` NULL) would never
    match. At login the id is known: fill it in on every such invitation for this
    username. Invitations that already carry an id are left alone, so a later
    rename or a reused username cannot take them over. The caller commits.
    """
    result = session.execute(
        update(ConversationInvite)
        .where(
            ConversationInvite.mw_username == mw_username,
            ConversationInvite.mw_user_id.is_(None),
        )
        .values(mw_user_id=mw_user_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def remove_conversation_invite(session, *, conversation_id: int, invite_id: int):
    invite = ConversationInvite.query.filter_by(
        id=invite_id, conversation_id=conversation_id,
    ).first()
    if invite is None:
        raise InvitationNotInConversation()
    username = invite.mw_username
    session.delete(invite)
    session.commit()
    return username


def add_conversation_invites(session, *, conversation_id: int,
                             usernames: Iterable[str],
                             invited_by: str | None = None) -> InviteBatchResult:
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
                    target = Participant.query.filter_by(
                        mw_username=username,
                    ).first()
                    session.add(ConversationInvite(
                        conversation_id=conversation_id,
                        mw_username=username,
                        mw_user_id=target.mw_user_id if target else None,
                        invited_by=invited_by,
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
