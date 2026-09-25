"""Transactional invitation commands shared by HTML and API adapters."""

import re

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
            # Bound to an account id: the name already belonged to an account that
            # had logged in (add_conversation_invites), or that account has logged
            # in since (claim_username_invites). Rows from the migration backfill
            # carry an id too. It says nothing about this consultation.
            'signedIn': row.mw_user_id is not None,
        } for row in rows],
        'capabilities': {'manageInvitations': True},
        'links': {'self': self_link, 'conversation': conversation_link},
    }


class InvitationNotInConversation(LookupError):
    pass


def canonical_mw_username(name: str) -> str:
    """A Wikimedia user name as MediaWiki stores it.

    Underscores are spaces, runs of spaces collapse, and the first letter is
    upper-case (Wikimedia wikis capitalise it). Everything else is compared
    exactly: "Alice" and "ALICE" are different accounts. Comparing in Python
    also sidesteps the database collation, which on MariaDB ignores case and
    accents.
    """
    name = re.sub(r'[\s_]+', ' ', name or '').strip()
    return name[:1].upper() + name[1:]


def _exact_wikimedia_participant(username: str) -> Participant | None:
    """The one account whose stored name equals *username* exactly."""
    for candidate in Participant.query.filter_by(mw_username=username).all():
        if candidate.mw_username == username and candidate.mw_user_id is not None:
            return candidate
    return None


def claim_username_invites(session, *, mw_user_id: int, mw_username: str) -> int:
    """Bind invitations made by user name to the account now logging in.

    The invite-only check matches the stable Wikimedia user id, so an invitation
    added for someone who had not logged in yet (``mw_user_id`` NULL) would never
    match. On every login the id is known: an unbound invitation whose name is
    exactly this account's canonical name is bound to it. An invitation that
    already carries an id is never re-bound, so a renamed or reused user name
    cannot take it over. The caller commits.

    Unbound invitations are few (only people who have never logged in), so they
    are matched in Python, exactly, rather than trusting the column collation.
    """
    name = canonical_mw_username(mw_username)
    unbound = session.execute(
        select(ConversationInvite.id, ConversationInvite.mw_username)
        .where(ConversationInvite.mw_user_id.is_(None))
    ).all()
    ids = [row.id for row in unbound if canonical_mw_username(row.mw_username) == name]
    if not ids:
        return 0
    result = session.execute(
        update(ConversationInvite)
        .where(ConversationInvite.id.in_(ids), ConversationInvite.mw_user_id.is_(None))
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

    Names are stored in MediaWiki's canonical form, so "foo_bar" and "Foo bar"
    are one invitation and match the name the login returns. An invitation is
    bound to an existing account only on an exact name match; otherwise it is
    claimed at that person's login (claim_username_invites).

    Each insert gets a savepoint. A concurrent unique-key winner rolls back only
    that username; an unrelated database failure rolls back the whole command.
    """
    submitted = [canonical_mw_username(name) for name in usernames]
    submitted = [name for name in submitted if name]
    candidates = list(dict.fromkeys(submitted))
    duplicate_inputs = len(submitted) - len(candidates)

    try:
        existing = {canonical_mw_username(name) for name in session.scalars(
            select(ConversationInvite.mw_username).where(
                ConversationInvite.conversation_id == conversation_id)
        )}
        pending = [username for username in candidates if username not in existing]
        added = 0
        concurrent_conflicts = 0

        for username in pending:
            try:
                with session.begin_nested():
                    target = _exact_wikimedia_participant(username)
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
