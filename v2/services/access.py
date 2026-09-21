"""Shared access decisions for participant-facing conversation APIs.

The provider answers whether an authenticated account is admitted.  This module
keeps that answer separate from the viewer relationship used by API refusals so
an unknown provider result cannot be mistaken for a known refusal.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from db import ConversationInvite, VoucherCode


AccessState = Literal['authorised', 'refused', 'unknown']
Certainty = Literal['known', 'temporary', 'inconclusive']
ViewerState = Literal['logged_out', 'refused', 'access_lost']
GatingType = Literal['invite_only', 'voucher', 'wiki_based']

GATING_TYPES = ('invite_only', 'voucher', 'wiki_based')


@dataclass(frozen=True)
class AccessAnswer:
    """The provider result for one authenticated account."""

    state: AccessState
    reason: str | None = None
    certainty: Certainty = 'known'

    def __post_init__(self) -> None:
        if self.state in {'authorised', 'refused'} and self.certainty != 'known':
            raise ValueError('known access states must have known certainty')
        if self.state == 'unknown' and self.certainty not in {
            'temporary', 'inconclusive',
        }:
            raise ValueError('unknown access must be temporary or inconclusive')
        if self.state == 'authorised' and self.reason is not None:
            raise ValueError('authorised access cannot have a refusal reason')
        if self.state in {'refused', 'unknown'} and not self.reason:
            raise ValueError('refused and unknown access require a reason key')


@dataclass(frozen=True)
class AccessDecision:
    """The shared check result, including the three refusal viewer states."""

    allowed: bool
    viewer: ViewerState | None
    answer: AccessAnswer | None
    gating_type: str | None
    certainty: Certainty = 'known'
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.allowed and self.viewer is not None:
            raise ValueError('an allowed decision has no refusal viewer state')
        if self.answer is not None:
            if self.certainty != self.answer.certainty:
                raise ValueError('decision certainty must match its answer')
            if self.reason != self.answer.reason:
                raise ValueError('decision reason must match its answer')
        if not self.allowed and self.viewer is None:
            raise ValueError('a denied decision requires a viewer state')


AccessProvider = Callable[[object, object], AccessAnswer]


class AccessRequired(RuntimeError):
    """Raised by the shared check when a request has no current access."""

    def __init__(self, conversation, decision: AccessDecision):
        super().__init__('access to this consultation is required')
        self.conversation = conversation
        self.decision = decision

    def details(self) -> dict:
        """Return the stable refusal payload shared by every API endpoint.

        ``loginOptions`` and ``sharedResults`` are deliberately explicit
        projections for the login prompt and results-only surface. This lane
        owns the shared gate, not those surfaces, so it returns empty lists
        until their links can be populated by the visibility/results work.
        """
        return {
            'slug': self.conversation.slug,
            'title': self.conversation.title,
            'gatingType': self.decision.gating_type,
            'viewer': self.decision.viewer,
            'certainty': self.decision.certainty,
            'reason': self.decision.reason,
            'loginOptions': [],
            'sharedResults': [],
        }


def is_demo_conversation(conversation) -> bool:
    """Demo remains a separate kind of process, outside the gating settings."""
    return conversation.access_policy == 'demo'


def is_gated_conversation(conversation) -> bool:
    """Read the new setting, with compatibility for pre-migration rows/tests."""
    return bool(
        getattr(conversation, 'gated', False)
        or getattr(conversation, 'gating_type', None)
        or conversation.access_policy == 'invite_only'
    ) and not is_demo_conversation(conversation)


def conversation_gating_type(conversation) -> str | None:
    value = getattr(conversation, 'gating_type', None)
    if value:
        return value
    if conversation.access_policy == 'invite_only':
        return 'invite_only'
    return None


def answer_invite_only(conversation, participant) -> AccessAnswer:
    """Resolve invite-only access by the stable Wikimedia user id only."""
    if participant.mw_user_id is None:
        return AccessAnswer(
            'refused',
            reason='access-invite-required',
        )
    invited = ConversationInvite.query.filter(
        ConversationInvite.conversation_id == conversation.id,
        ConversationInvite.mw_user_id == participant.mw_user_id,
    ).first()
    if invited is not None:
        return AccessAnswer('authorised')
    return AccessAnswer(
        'refused',
        reason='access-invite-required',
    )


def _unimplemented_provider_answer(conversation, participant) -> AccessAnswer:
    """Fail closed until the provider-specific lane supplies its adapter.

    Selecting ``wiki_based`` before that adapter is wired makes every account
    unknown/inconclusive with no access, rather than accidentally opening the
    conversation. Provider lanes integrate by replacing the corresponding entry
    in ``DEFAULT_PROVIDERS``.
    """
    del conversation, participant
    return AccessAnswer(
        'unknown',
        reason='access-could-not-confirm',
        certainty='inconclusive',
    )


def answer_voucher(conversation, participant) -> AccessAnswer:
    """Voucher provider (#368): admits the one account that redeemed a voucher
    for this conversation, unless the organizer has revoked it."""
    if (participant is None
            or participant.account_kind != 'voucher'
            or participant.conversation_id != conversation.id):
        return AccessAnswer('refused', reason='access-voucher-required')

    voucher = VoucherCode.query.filter_by(
        participant_id=participant.id,
    ).first()
    if voucher is not None and voucher.status == 'revoked':
        return AccessAnswer('refused', reason='access-voucher-revoked')
    return AccessAnswer('authorised')


# Provider-lane integration seam: each provider replaces its entry here while
# the shared check and refusal/viewer mapping remain provider-neutral.
DEFAULT_PROVIDERS: Mapping[str, AccessProvider] = {
    'invite_only': answer_invite_only,
    'voucher': answer_voucher,
    'wiki_based': _unimplemented_provider_answer,
}


def check_access(
    conversation,
    participant,
    *,
    demo_session: bool = False,
    demo_conversation_id: int | None = None,
    participation=None,
    providers: Mapping[str, AccessProvider] | None = None,
) -> AccessDecision:
    """Return one shared access decision for every read and action endpoint.

    Logged-out viewers never reach a provider.  A ``Participation`` is used only
    to classify a refusal as ``access_lost``; it never grants access by itself.
    """
    if demo_session:
        if (is_demo_conversation(conversation)
                and demo_conversation_id == conversation.id):
            answer = AccessAnswer('authorised')
            return AccessDecision(
                allowed=True, viewer=None, answer=answer, gating_type=None,
                certainty=answer.certainty, reason=answer.reason,
            )
        answer = AccessAnswer('refused', reason='access-demo-scope')
        return AccessDecision(
            allowed=False, viewer='refused', answer=answer, gating_type=None,
            certainty=answer.certainty, reason=answer.reason,
        )

    # The demo route binds its own session before calling the check. A demo
    # conversation reached through a normal account keeps the existing automatic
    # demo-participation behaviour and is not governed by gated settings.
    if is_demo_conversation(conversation) or not is_gated_conversation(conversation):
        answer = AccessAnswer('authorised')
        return AccessDecision(
            allowed=True, viewer=None, answer=answer,
            gating_type=None, certainty=answer.certainty, reason=answer.reason,
        )

    gating_type = conversation_gating_type(conversation)
    if participant is None:
        return AccessDecision(
            allowed=False, viewer='logged_out', answer=None,
            gating_type=gating_type, certainty='known', reason=None,
        )

    if participation is None:
        from db import Participation  # local import avoids a model-only hot path
        participation = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conversation.id,
        ).first()

    provider_map = providers or DEFAULT_PROVIDERS
    provider = provider_map.get(gating_type)
    answer = (
        provider(conversation, participant)
        if provider is not None
        else AccessAnswer(
            'unknown', reason='access-policy-not-configured',
            certainty='inconclusive',
        )
    )
    viewer: ViewerState = 'access_lost' if participation else 'refused'
    return AccessDecision(
        allowed=answer.state == 'authorised',
        viewer=None if answer.state == 'authorised' else viewer,
        answer=answer,
        gating_type=gating_type,
        certainty=answer.certainty,
        reason=answer.reason,
    )
