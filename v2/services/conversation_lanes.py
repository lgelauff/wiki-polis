"""Participant-facing conversation lane projections shared by HTML and JSON."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timezone
from typing import Literal

from sqlalchemy.orm import joinedload

from db import (AdminRole, Conversation, ConversationInvite, Participant,
                Participation, db)

ConversationBucket = Literal['needs_attention', 'caught_up', 'inactive', 'archived']

ACTION_PHASES = frozenset({'submission', 'argument_mapping', 'informed_voting'})


def participant_can_act(*, active: bool, paused: bool,
                        phases: set[str] | frozenset[str]) -> bool:
    """Return whether participant-facing work is open in the current state."""
    return active and not paused and bool(set(phases) & ACTION_PHASES)


def classify_joined_conversation(
    *,
    active: bool,
    paused: bool,
    phases: set[str] | frozenset[str],
    statements_remaining: int | None,
) -> ConversationBucket:
    """Classify an open record by what its participant can do right now.

    Explore is currently the only phase with a reliable per-participant completion
    signal. Other action phases remain in ``needs_attention`` until equivalent
    argument/informed-vote signals exist.
    """
    if not active:
        return 'archived'
    action_phases = set(phases) & ACTION_PHASES
    if paused or not action_phases:
        return 'inactive'
    if action_phases == {'submission'} and statements_remaining == 0:
        return 'caught_up'
    return 'needs_attention'


def scheduled_transition(conv: Conversation) -> dict | None:
    at = conv.scheduled_transition_at
    target = conv.scheduled_transition_target
    if at is None or not target or conv.scheduled_transition_frozen:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    labels = {
        'submission': 'Explore',
        'featured_selection': 'Featured selection',
        'argument_mapping': 'Arguments',
        'cleanup': 'Cleanup',
        'informed_voting': 'Informed vote',
        'public_results': 'Report',
        'closed': 'Closed',
    }
    return {
        'at': at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'target': target,
        'targetLabel': labels.get(target, target.replace('_', ' ').title()),
    }


@dataclass
class ConversationLane:
    """Canonical lane state; adapters choose HTML context or browser DTO."""

    space: Literal['real', 'demo']
    authenticated: bool
    public_conversations: list[Conversation] = field(default_factory=list)
    attention_joined: list[Conversation] = field(default_factory=list)
    caught_up_joined: list[Conversation] = field(default_factory=list)
    inactive_joined: list[Conversation] = field(default_factory=list)
    archived_joined: list[Conversation] = field(default_factory=list)
    available: list[Conversation] = field(default_factory=list)
    moderating: list[Conversation] = field(default_factory=list)
    pseudonym_map: dict[int, Participation] = field(default_factory=dict)
    signals_map: dict[int, dict] = field(default_factory=dict)

    def template_context(self) -> dict:
        return {
            'public_conversations': self.public_conversations,
            'attention_joined': self.attention_joined,
            'caught_up_joined': self.caught_up_joined,
            'inactive_joined': self.inactive_joined,
            'archived_joined': self.archived_joined,
            'available': self.available,
            'moderating': self.moderating,
            'pseudonym_map': self.pseudonym_map,
            'signals_map': self.signals_map,
        }

    def to_api(self, *, conversation_link: Callable[[str], str],
               about_link: Callable[[str], str],
               explore_link: Callable[[str], str],
               arguments_link: Callable[[str], str],
               informed_voting_link: Callable[[str], str],
               results_link: Callable[[str], str],
               reveal_link: Callable[[str], str],
               admin_link: Callable[[int], str]) -> dict:
        moderated_ids = {conv.id for conv in self.moderating}

        def card(conv: Conversation, relationship: str,
                 bucket: ConversationBucket | None = None) -> dict:
            signal = self.signals_map.get(conv.id, {})
            participation = self.pseudonym_map.get(conv.id)
            phases = sorted(signal.get('phases', set()))
            action_open = participant_can_act(
                active=conv.active, paused=conv.paused, phases=set(phases),
            )
            outputs = [
                {
                    'key': item['key'],
                    'label': item['label'],
                    'status': item['status'],
                    'symbol': item['symbol'],
                    'tooltip': item['tooltip'],
                    'pending': item['pending'],
                    'ready': bool(item['ready']),
                    'href': item.get('href'),
                }
                for item in signal.get('outputs', [])
            ]
            reveal = signal.get('reveal')
            closed_at = conv.closed_at
            if closed_at is not None:
                closed_at = (
                    closed_at if closed_at.tzinfo
                    else closed_at.replace(tzinfo=timezone.utc)
                ).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            links = {
                'self': conversation_link(conv.slug),
                'about': about_link(conv.slug),
            }
            if relationship == 'joined' and action_open and 'submission' in phases:
                links['explore'] = explore_link(conv.slug)
            if relationship == 'joined' and action_open and 'argument_mapping' in phases:
                links['arguments'] = arguments_link(conv.slug)
            if relationship == 'joined' and action_open and 'informed_voting' in phases:
                links['informedVoting'] = informed_voting_link(conv.slug)
            if relationship == 'joined' and any(
                output['ready'] and output['key'] in {'preliminary-results', 'report'}
                for output in outputs
            ):
                links['results'] = results_link(conv.slug)
            if relationship == 'joined' and signal.get('reveal') is not None:
                links['identityReveal'] = reveal_link(conv.slug)
            if conv.id in moderated_ids:
                links['admin'] = admin_link(conv.id)
            return {
                'slug': conv.slug,
                'title': conv.title,
                'relationship': relationship,
                'participantState': bucket,
                'pseudonym': participation.pseudonym if participation else None,
                'status': ('archived' if not conv.active else
                           'paused' if conv.paused else 'open'),
                'closedAt': closed_at,
                'phases': phases,
                'statementsRemaining': signal.get('statements_remaining'),
                'scheduledTransition': scheduled_transition(conv),
                'reveal': ({
                    'state': reveal['state'],
                    'daysRemaining': reveal['days_left'],
                } if reveal else None),
                'outputs': outputs,
                'capabilities': {
                    'join': relationship == 'available' and self.authenticated,
                    'participate': relationship == 'joined' and action_open,
                    'moderate': conv.id in moderated_ids,
                },
                'links': links,
            }

        joined_groups = {
            'needsAttention': [card(c, 'joined', 'needs_attention')
                               for c in self.attention_joined],
            'caughtUp': [card(c, 'joined', 'caught_up') for c in self.caught_up_joined],
            'inactive': [card(c, 'joined', 'inactive') for c in self.inactive_joined],
            'archived': [card(c, 'joined', 'archived') for c in self.archived_joined],
        }
        public = self.public_conversations if not self.authenticated else self.available
        return {
            'space': self.space,
            'authenticated': self.authenticated,
            'groups': {
                **joined_groups,
                'available': [card(c, 'available') for c in public],
                'moderating': [card(c, 'moderating') for c in self.moderating],
            },
        }


def build_conversation_lane(
    *,
    demo: bool,
    username: str | None,
    participant: Participant | None,
    global_admin: bool,
    active_phases: Callable[[Conversation], set[str]],
    output_items: Callable[[Conversation], list[dict]],
    reveal_context: Callable[[Conversation, Participation | None], dict | None],
    polis_client,
) -> ConversationLane:
    """Load one demo/real lane and compute participant-facing state once."""
    lane = ConversationLane(space='demo' if demo else 'real', authenticated=bool(username))
    if not username:
        query = Conversation.query.filter_by(active=True, paused=False)
        query = (query.filter_by(access_policy='demo') if demo else
                 query.filter(Conversation.access_policy == 'public'))
        lane.public_conversations = query.order_by(Conversation.created_at.desc()).all()
        lane.signals_map = {
            conv.id: {
                'phases': active_phases(conv),
                'outputs': output_items(conv),
                'scheduled_transition': scheduled_transition(conv),
            }
            for conv in lane.public_conversations
        }
        return lane

    joined_parts = (
        Participation.query
        .options(joinedload(Participation.conversation))
        .filter_by(participant_id=participant.id).all()
        if participant else []
    )
    joined_ids = {part.conversation_id for part in joined_parts}
    lane_parts = [
        part for part in joined_parts
        if part.conversation and (part.conversation.access_policy == 'demo') == demo
    ]
    joined_conversations = [part.conversation for part in lane_parts]

    if demo:
        available_query = (Conversation.query
                           .filter_by(active=True, paused=False, access_policy='demo'))
    else:
        invited_ids = [
            invite.conversation_id
            for invite in ConversationInvite.query.filter_by(mw_username=username).all()
        ]
        available_query = (Conversation.query
                           .filter_by(active=True, paused=False)
                           .filter(db.or_(
                               Conversation.access_policy == 'public',
                               db.and_(
                                   Conversation.access_policy == 'invite_only',
                                   Conversation.id.in_(invited_ids or [0]),
                               ),
                           )))
    lane.available = (available_query
                      .filter(~Conversation.id.in_(joined_ids or [0]))
                      .order_by(Conversation.created_at.desc()).all())

    moderated_ids: set[int] = set()
    if participant:
        if global_admin:
            lane.moderating = Conversation.query.order_by(Conversation.created_at.desc()).all()
            moderated_ids = {conv.id for conv in lane.moderating}
        else:
            roles = AdminRole.query.filter_by(participant_id=participant.id).all()
            moderated_ids = {role.conversation_id for role in roles}
            if moderated_ids:
                lane.moderating = Conversation.query.filter(
                    Conversation.id.in_(moderated_ids),
                ).all()
    lane.moderating = [
        conv for conv in lane.moderating
        if (conv.access_policy == 'demo') == demo
    ]
    lane.available = [conv for conv in lane.available if conv.id not in moderated_ids]
    lane.pseudonym_map = {part.conversation_id: part for part in lane_parts}

    all_conversations = joined_conversations + lane.available
    submission_conversations = [
        conv for conv in joined_conversations if conv.phase_submission and conv.active
    ]
    zinvites = [conv.polis_id for conv in submission_conversations if conv.polis_id]
    remaining_by_zinvite = {}
    if zinvites and participant:
        result = polis_client.get_statements_remaining_bulk(zinvites, participant.xid)
        if result:
            remaining_by_zinvite = result

    for conv in all_conversations:
        participation = lane.pseudonym_map.get(conv.id)
        lane.signals_map[conv.id] = {
            'phases': active_phases(conv),
            'outputs': output_items(conv),
            'statements_remaining': remaining_by_zinvite.get(conv.polis_id),
            'reveal': reveal_context(conv, participation) if conv.closed_at else None,
            'scheduled_transition': scheduled_transition(conv),
        }

    buckets: dict[ConversationBucket, list[Conversation]] = {
        'needs_attention': [], 'caught_up': [], 'inactive': [], 'archived': [],
    }
    for conv in joined_conversations:
        signal = lane.signals_map[conv.id]
        bucket = classify_joined_conversation(
            active=conv.active,
            paused=conv.paused,
            phases=signal['phases'],
            statements_remaining=signal['statements_remaining'],
        )
        buckets[bucket].append(conv)
    lane.attention_joined = buckets['needs_attention']
    lane.caught_up_joined = buckets['caught_up']
    lane.inactive_joined = buckets['inactive']
    lane.archived_joined = buckets['archived']
    return lane
