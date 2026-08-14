"""Conversation About read model shared by participant HTML and API adapters."""

from collections.abc import Callable
from dataclasses import dataclass

from db import (Argument, ArgumentVote, AuditEvent, Conversation, FeaturedStatement,
                Participant, Participation, db)
from services.conversation_lanes import participant_can_act, scheduled_transition


def _personal_contributions(conv: Conversation, participation: Participation,
                            participant: Participant, polis_client) -> dict:
    arguments_added = (
        db.session.query(db.func.count(Argument.id))
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(
            FeaturedStatement.conversation_id == conv.id,
            Argument.proposer_pseudonym == participation.pseudonym,
        )
        .scalar() or 0
    )
    arguments_rated = (
        db.session.query(db.func.count(ArgumentVote.id))
        .join(Argument, ArgumentVote.argument_id == Argument.id)
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(
            FeaturedStatement.conversation_id == conv.id,
            ArgumentVote.participant_id == participant.id,
        )
        .scalar() or 0
    )
    statement_progress = None
    try:
        progress = polis_client.get_statement_progress_bulk([conv.polis_id], participant.xid)
        if progress:
            statement_progress = progress.get(conv.polis_id)
    except Exception:
        # About remains useful when the optional Polis stats connection is unavailable.
        statement_progress = None
    return {
        'statementsSuggested': len(participation.new_stmt_ids or []),
        'statementVotes': statement_progress.get('voted') if statement_progress else None,
        'statementVotesAvailable': statement_progress is not None,
        'argumentsAdded': int(arguments_added),
        'argumentsRated': int(arguments_rated),
    }


@dataclass
class ConversationAbout:
    conversation: Conversation
    participation: Participation | None
    phases: list[dict]
    outputs: list[dict]
    statistics: dict
    personal: dict | None
    moderation_log_count: int
    can_moderate: bool

    def template_context(self) -> dict:
        return {
            'conversation': self.conversation,
            'participation': self.participation,
            'phases': self.phases,
            'outputs': self.outputs,
            'statistics': self.statistics,
            'personal': self.personal,
            'moderation_log_count': self.moderation_log_count,
            'can_moderate': self.can_moderate,
            'scheduled_transition': scheduled_transition(self.conversation),
        }

    def to_api(self, *, self_link: str, conversation_link: str,
               moderation_log_link: str) -> dict:
        return {
            'slug': self.conversation.slug,
            'title': self.conversation.title,
            'space': 'demo' if self.conversation.access_policy == 'demo' else 'real',
            'descriptionHtml': self.conversation.intro_text,
            'outroHtml': self.conversation.outro_text,
            'status': ('archived' if not self.conversation.active else
                       'paused' if self.conversation.paused else 'open'),
            'phases': self.phases,
            'scheduledTransition': scheduled_transition(self.conversation),
            'pseudonym': self.participation.pseudonym if self.participation else None,
            'statistics': self.statistics,
            'personal': self.personal,
            'outputs': [
                {
                    'key': item['key'],
                    'label': item['label'],
                    'status': item['status'],
                    'ready': bool(item['ready']),
                    'href': item.get('href'),
                }
                for item in self.outputs
            ],
            'moderation': {
                'eventCount': self.moderation_log_count,
                'href': moderation_log_link,
            },
            'capabilities': {
                'participate': bool(self.participation) and participant_can_act(
                    active=self.conversation.active,
                    paused=self.conversation.paused,
                    phases={item['key'] for item in self.phases},
                ),
                'moderate': self.can_moderate,
            },
            'links': {'self': self_link, 'conversation': conversation_link},
        }


def build_conversation_about(
    *,
    conversation: Conversation,
    participant: Participant | None,
    participation: Participation | None,
    active_phases: Callable[[Conversation], set[str]],
    phase_labels: dict[str, str],
    output_items: Callable[[Conversation], list[dict]],
    polis_client,
    can_moderate: bool,
) -> ConversationAbout:
    phase_keys = active_phases(conversation)
    ordered_phase_keys = [key for key in phase_labels if key in phase_keys]
    ordered_phase_keys.extend(sorted(phase_keys - set(ordered_phase_keys)))
    phases = [
        {'key': key, 'label': phase_labels.get(key, key.replace('_', ' ').title())}
        for key in ordered_phase_keys
    ]
    polis_stats = None
    try:
        polis_stats = polis_client.get_polis_stats(conversation.polis_id)
    except Exception:
        polis_stats = None
    argument_counts = (
        db.session.query(
            db.func.count(Argument.id),
            db.func.count(db.distinct(Argument.proposer_pseudonym)),
        )
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(
            FeaturedStatement.conversation_id == conversation.id,
            Argument.hidden.is_(False),
            Argument.proposer_pseudonym.isnot(None),
        )
        .one()
    )
    statistics = {
        'participants': polis_stats.get('n_participants') if polis_stats else None,
        'statementVotes': polis_stats.get('n_votes') if polis_stats else None,
        'statements': polis_stats.get('n_statements') if polis_stats else None,
        'arguments': int(argument_counts[0] or 0),
        'argumentContributors': int(argument_counts[1] or 0),
    }
    personal = (
        _personal_contributions(conversation, participation, participant, polis_client)
        if participation and participant else None
    )
    moderation_log_count = AuditEvent.query.filter(
        AuditEvent.conversation_id == conversation.id,
        AuditEvent.operation.in_(('participant.ban', 'participant.unban')),
    ).count()
    return ConversationAbout(
        conversation=conversation,
        participation=participation,
        phases=phases,
        outputs=output_items(conversation),
        statistics=statistics,
        personal=personal,
        moderation_log_count=moderation_log_count,
        can_moderate=can_moderate,
    )
