"""Participation-entry read model shared by HTML and JSON adapters."""

from dataclasses import dataclass

from db import Conversation, Participant, Participation


@dataclass(frozen=True)
class ParticipationEntry:
    conversation: Conversation
    participant: Participant
    participation: Participation | None
    invited: bool
    can_moderate: bool
    emailable: bool
    pseudonyms: list[str]
    reveal_cooldown_days: int
    reveal_window_end_days: int

    @property
    def state(self) -> str:
        if self.conversation.access_policy == 'demo' or self.participation:
            return 'redirect'
        if self.conversation.access_policy == 'invite_only' and not self.invited:
            return 'invite_denied'
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
        if self.state == 'invite_denied':
            return {
                'state': 'invite_denied',
                'conversation': conversation,
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
    invited: bool,
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
        invited=invited,
        can_moderate=can_moderate,
        emailable=emailable,
        pseudonyms=pseudonyms,
        reveal_cooldown_days=reveal_cooldown_days,
        reveal_window_end_days=reveal_window_end_days,
    )
