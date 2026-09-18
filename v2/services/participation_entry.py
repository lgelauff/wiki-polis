"""Participation-entry read model shared by HTML and JSON adapters."""

from dataclasses import dataclass

from db import Conversation, Participant, Participation
from services.access import AccessDecision


@dataclass(frozen=True)
class ParticipationEntry:
    conversation: Conversation
    participant: Participant
    participation: Participation | None
    access: AccessDecision
    can_moderate: bool
    emailable: bool
    pseudonyms: list[str]
    reveal_cooldown_days: int
    reveal_window_end_days: int

    @property
    def invited(self) -> bool:
        """Compatibility projection; the shared check is authoritative."""
        return self.access.allowed

    @property
    def state(self) -> str:
        if self.conversation.access_policy == 'demo' and self.access.allowed:
            return 'redirect'
        if not self.access.allowed:
            return 'access_lost' if self.participation else 'invite_denied'
        if self.participation:
            return 'redirect'
        return 'join'

    def to_api(self, *, conversation_link: str, home_link: str,
               manage_invites_link: str | None) -> dict:
        if self.state == 'redirect':
            return {
                'state': 'redirect',
                'reason': ('demo' if self.conversation.access_policy == 'demo'
                           else 'already_participating'),
                'href': conversation_link,
            }
        conversation = {
            'id': self.conversation.id,
            'slug': self.conversation.slug,
            'title': self.conversation.title,
            'descriptionHtml': self.conversation.intro_text,
            'eligibilityLabel': self.conversation.eligibility_label,
        }
        if self.state in {'invite_denied', 'access_lost'}:
            return {
                'state': self.state,
                'conversation': {
                    'id': conversation['id'],
                    'slug': conversation['slug'],
                    'title': conversation['title'],
                },
                'viewer': self.access.viewer,
                'certainty': self.access.certainty,
                'reason': self.access.reason,
                'sharedResults': [],
                'canModerate': self.can_moderate,
                'links': {
                    'home': home_link,
                    'manageInvites': manage_invites_link if self.can_moderate else None,
                },
            }
        return {
            'state': 'join',
            'conversation': conversation,
            'pseudonyms': self.pseudonyms,
            'emailable': self.emailable,
            'reveal': {
                'cooldownDays': self.reveal_cooldown_days,
                'windowEndDays': self.reveal_window_end_days,
            },
            'links': {'home': home_link, 'conversation': conversation_link},
        }


def build_participation_entry(
    *,
    conversation: Conversation,
    participant: Participant,
    access: AccessDecision,
    can_moderate: bool,
    emailable: bool,
    pseudonyms: list[str],
    reveal_cooldown_days: int,
    reveal_window_end_days: int,
) -> ParticipationEntry:
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conversation.id,
    ).first()
    return ParticipationEntry(
        conversation=conversation,
        participant=participant,
        participation=participation,
        access=access,
        can_moderate=can_moderate,
        emailable=emailable,
        pseudonyms=pseudonyms,
        reveal_cooldown_days=reveal_cooldown_days,
        reveal_window_end_days=reveal_window_end_days,
    )
