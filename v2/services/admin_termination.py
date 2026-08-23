"""Conversation termination projection and guarded empty-conversation deletion."""

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError


def build_termination_state(
    *, conversation, valid_vote_count: int | None,
    self_link: str, lifecycle_link: str,
) -> dict:
    if valid_vote_count is None:
        deletion = {
            'state': 'unavailable', 'validVoteCount': None,
            'reason': 'Voting data could not be verified.',
        }
    elif valid_vote_count:
        deletion = {
            'state': 'blocked_by_votes', 'validVoteCount': valid_vote_count,
            'reason': 'Conversations with votes are retained; archive it instead.',
        }
    else:
        deletion = {
            'state': 'eligible', 'validVoteCount': 0,
            'reason': 'No valid votes were found.',
        }
    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
        },
        'deletion': deletion,
        'links': {'self': self_link, 'lifecycle': lifecycle_link},
    }


class DeletionVerificationUnavailable(RuntimeError):
    pass


class DeletionBlockedByVotes(RuntimeError):
    def __init__(self, count: int):
        self.count = count


class DeletionUpstreamFailed(RuntimeError):
    pass


class DeletionOutcomeUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class DeletionResult:
    conversation_id: int
    slug: str


def delete_empty_conversation(
    *, conversation, valid_vote_count: int | None, hide_upstream,
    delete_local, session, audit_deleted, upstream_errors: tuple[type[Exception], ...],
) -> DeletionResult:
    if valid_vote_count is None:
        raise DeletionVerificationUnavailable()
    if valid_vote_count != 0:
        raise DeletionBlockedByVotes(valid_vote_count)
    conversation_id = conversation.id
    slug = conversation.slug
    try:
        hide_upstream(conversation.polis_id)
    except upstream_errors as exc:
        raise DeletionUpstreamFailed() from exc
    try:
        delete_local(conversation)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise DeletionOutcomeUnknown() from exc
    audit_deleted(conversation_id)
    return DeletionResult(conversation_id=conversation_id, slug=slug)
