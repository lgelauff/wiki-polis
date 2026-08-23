"""Site-wide administration projection and local membership commands."""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def build_admin_catalog(
    *, conversations, global_admins, phase_routes: dict,
    managed_creation: bool, self_link: str, conversation_link,
) -> dict:
    def status(conversation) -> str:
        if conversation.closed_at:
            return 'closed'
        if not conversation.active:
            return 'archived'
        if conversation.paused:
            return 'paused'
        return 'active'

    return {
        'conversations': [{
            'id': row.id,
            'slug': row.slug,
            'title': row.title,
            'accessPolicy': row.access_policy,
            'status': status(row),
            'createdAt': row.created_at.isoformat() if row.created_at else None,
            'links': {
                'participant': f'/c/{row.slug}',
                'manage': conversation_link(row.id),
            },
        } for row in conversations],
        'globalAdmins': [{
            'participantId': row.id,
            'username': row.mw_username,
        } for row in global_admins],
        'phaseRoutes': [{
            'key': key,
            'label': route['label'],
            'description': route['description'],
        } for key, route in phase_routes.items()],
        'creation': {
            'mode': 'managed' if managed_creation else 'manual_polis_id',
            'defaultModerationPolicy': 'moderate',
        },
        'links': {'self': self_link},
    }


class ConversationSlugConflict(RuntimeError):
    pass


class ConversationCreationUpstreamFailed(RuntimeError):
    pass


class ConversationCreationSaveFailed(RuntimeError):
    def __init__(self, *, outcome_unknown: bool):
        self.outcome_unknown = outcome_unknown


class GlobalAdminParticipantNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversationCreationResult:
    conversation: object


def create_conversation(
    *, fields: dict, existing_slug: bool, managed_creation: bool,
    create_upstream, conversation_factory, session, audit,
    upstream_errors: tuple[type[Exception], ...],
) -> ConversationCreationResult:
    if existing_slug:
        raise ConversationSlugConflict()
    upstream_created = False
    if managed_creation:
        try:
            polis_id = create_upstream(fields['title'])
            upstream_created = True
        except upstream_errors as exc:
            raise ConversationCreationUpstreamFailed() from exc
    else:
        polis_id = fields['polis_id']

    conversation = conversation_factory(polis_id)
    session.add(conversation)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if not upstream_created:
            raise ConversationSlugConflict() from exc
        raise ConversationCreationSaveFailed(outcome_unknown=True) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise ConversationCreationSaveFailed(
            outcome_unknown=upstream_created,
        ) from exc
    audit(conversation.id, conversation.slug)
    return ConversationCreationResult(conversation=conversation)


def set_global_admin(*, participant, granted: bool, session, audit) -> bool:
    if participant is None:
        raise GlobalAdminParticipantNotFound()
    changed = bool(participant.is_global_admin) != granted
    if changed:
        participant.is_global_admin = granted
        session.commit()
        audit(participant.id, granted)
    else:
        session.commit()
    return changed
