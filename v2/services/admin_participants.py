"""Admin participant roster projection and conversation-access command."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import nh3
from sqlalchemy.orm import joinedload

from db import (Argument, ArgumentVote, Conversation, ConversationBan,
                FeaturedStatement, Participant, Participation, db)


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class AdminParticipantRow:
    participation: Participation
    participant: Participant
    statement_progress: dict | None
    arguments_submitted: int
    arguments_voted: int
    active_ban: ConversationBan | None

    def to_api(self) -> dict:
        progress = self.statement_progress
        return {
            'participantId': self.participant.id,
            'username': self.participant.mw_username,
            'pseudonym': self.participation.pseudonym,
            'statementProgress': ({
                'total': int(progress['total']),
                'voted': int(progress['voted']),
                'remaining': int(progress['remaining']),
            } if progress is not None else None),
            'arguments': {
                'submitted': self.arguments_submitted,
                'prioritized': self.arguments_voted,
            },
            'lastEngagementAt': _utc_iso(self.participation.last_engagement),
            'access': {
                'banned': self.active_ban is not None,
                'changedAt': _utc_iso(
                    self.active_ban.created_at if self.active_ban else None,
                ),
                'summary': self.active_ban.summary if self.active_ban else None,
            },
        }


@dataclass(frozen=True)
class AdminParticipantRoster:
    conversation: Conversation
    rows: list[AdminParticipantRow]
    statement_progress_unavailable: bool

    def to_api(self, *, self_link: str, conversation_link: str) -> dict:
        return {
            'conversation': {
                'id': self.conversation.id,
                'slug': self.conversation.slug,
                'title': self.conversation.title,
            },
            'participants': [row.to_api() for row in self.rows],
            'dataAvailability': {
                'statementProgress': not self.statement_progress_unavailable,
            },
            'capabilities': {'setParticipantAccess': True},
            'links': {
                'self': self_link,
                'conversation': conversation_link,
            },
        }


def build_admin_participant_roster(
    *, conversation: Conversation, polis_client, polis_pg_configured: bool,
    participant_subject: Callable[[Participant], str],
) -> AdminParticipantRoster:
    """Build the single roster read model used by HTML and JSON adapters."""
    participations = (
        Participation.query
        .join(Participant)
        .filter(Participation.conversation_id == conversation.id)
        .options(joinedload(Participation.participant))
        .order_by(Participant.mw_username)
        .all()
    )
    submitted_counts = dict(
        db.session.query(Argument.proposer_pseudonym, db.func.count(Argument.id))
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(
            FeaturedStatement.conversation_id == conversation.id,
            Argument.proposer_pseudonym.isnot(None),
        )
        .group_by(Argument.proposer_pseudonym)
        .all()
    )
    voted_counts = dict(
        db.session.query(ArgumentVote.participant_id, db.func.count(ArgumentVote.id))
        .join(Argument, ArgumentVote.argument_id == Argument.id)
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(FeaturedStatement.conversation_id == conversation.id)
        .group_by(ArgumentVote.participant_id)
        .all()
    )

    progress_by_subject = None
    progress_subjects = {
        participation.participant_id: participant_subject(participation.participant)
        for participation in participations
    }
    if polis_pg_configured:
        progress_by_subject = polis_client.get_statement_progress_for_participants(
            conversation.polis_id, list(progress_subjects.values()),
        )
    statement_progress_unavailable = (
        polis_pg_configured and progress_by_subject is None
    )
    active_bans = {
        ban.participant_id: ban
        for ban in ConversationBan.query.filter_by(
            conversation_id=conversation.id, lifted_at=None,
        ).all()
    }
    rows = []
    for participation in participations:
        progress = (
            progress_by_subject.get(progress_subjects[participation.participant_id])
            if progress_by_subject is not None else None
        )
        rows.append(AdminParticipantRow(
            participation=participation,
            participant=participation.participant,
            statement_progress=progress,
            arguments_submitted=int(submitted_counts.get(participation.pseudonym, 0)),
            arguments_voted=int(voted_counts.get(participation.participant_id, 0)),
            active_ban=active_bans.get(participation.participant_id),
        ))
    return AdminParticipantRoster(
        conversation=conversation,
        rows=rows,
        statement_progress_unavailable=statement_progress_unavailable,
    )


class ParticipantNotInConversation(LookupError):
    pass


@dataclass(frozen=True)
class ParticipantAccessResult:
    participant_id: int
    banned: bool
    changed: bool
    changed_at: datetime | None
    summary: str | None


def set_participant_access(
    *, conversation: Conversation, participant_id: int, banned: bool,
    summary: str | None, actor: Participant | None, audit,
) -> ParticipantAccessResult:
    """Replace one participant's ban state, safely replaying identical requests."""
    participation = (
        Participation.query
        .filter_by(
            conversation_id=conversation.id,
            participant_id=participant_id,
        )
        .with_for_update()
        .first()
    )
    if participation is None:
        raise ParticipantNotInConversation()

    active_ban = ConversationBan.query.filter_by(
        conversation_id=conversation.id,
        participant_id=participant_id,
        lifted_at=None,
    ).first()
    clean_summary = nh3.clean((summary or '').strip(), tags=frozenset())[:1000]
    changed = False
    operation = None
    changed_at = None
    if banned and active_ban is None:
        active_ban = ConversationBan(
            conversation_id=conversation.id,
            participant_id=participant_id,
            banned_by_id=actor.id if actor else None,
            summary=clean_summary or None,
        )
        db.session.add(active_ban)
        db.session.commit()
        changed = True
        operation = 'participant.ban'
        changed_at = active_ban.created_at
    elif not banned and active_ban is not None:
        active_ban.lifted_at = datetime.now(timezone.utc)
        active_ban.lifted_by_id = actor.id if actor else None
        active_ban.lift_summary = clean_summary or None
        db.session.commit()
        changed = True
        operation = 'participant.unban'
        changed_at = active_ban.lifted_at

    if not changed:
        # Release the membership row lock before serializing the replay receipt.
        db.session.commit()

    if operation:
        audit(
            operation,
            conv_id=conversation.id,
            target_type='participant',
            target_id=participant_id,
            scope='conversation',
            summary_present=bool(clean_summary),
        )
    if not changed and active_ban is not None:
        changed_at = active_ban.created_at
    return ParticipantAccessResult(
        participant_id=participant_id,
        banned=banned,
        changed=changed,
        changed_at=changed_at,
        summary=(active_ban.summary if banned and active_ban else clean_summary or None),
    )
