"""Site-wide administration projection and local membership commands."""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def conversation_status(conversation) -> str:
    """One word for where a consultation stands, shared by the dashboard and Admin home."""
    if conversation.closed_at:
        return 'closed'
    if not conversation.active:
        return 'archived'
    if conversation.paused:
        return 'paused'
    return 'active'


def build_admin_catalog(
    *, conversations, global_admins, phase_routes: dict,
    managed_creation: bool, self_link: str, conversation_link,
) -> dict:
    status = conversation_status

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


# The server's role identifiers, as `_conversation_role_label` (app.py) sends them, so the
# console's `roleLabel` maps them to its own words. Organizer outranks Moderator: someone
# who holds both rows for one consultation is shown as its organizer.
_HOME_ROLE_LABELS = {'organizer': 'Organizer', 'moderator': 'Moderator'}


def build_admin_home(
    *, roles, open_flags: dict, site_admin: bool, self_link: str,
    conversation_link, site_admin_link: str,
) -> dict:
    """The Admin home (#538): the consultations the caller holds a role in, and nothing else.

    ``roles`` are the caller's own ``AdminRole`` rows; a site admin's are listed like
    anyone's (site-wide access is not a role in a consultation, so it adds no rows).
    ``open_flags`` maps a conversation id to its open flag count. No participant data:
    titles, the caller's own role, a status word and a count.
    """
    by_conversation: dict[int, tuple] = {}
    for role in roles:
        conversation = role.conversation
        held = by_conversation.get(conversation.id)
        if held is None or role.role == 'organizer':
            by_conversation[conversation.id] = (conversation, role.role)
    rows = sorted(
        by_conversation.values(),
        # Newest first, as the dashboard lists them; a row without a date goes last.
        key=lambda item: (item[0].created_at is not None, item[0].created_at or 0, item[0].id),
        reverse=True,
    )
    return {
        'conversations': [{
            'id': conversation.id,
            'title': conversation.title,
            'role': _HOME_ROLE_LABELS[role],
            'status': conversation_status(conversation),
            'openFlags': int(open_flags.get(conversation.id, 0)),
            'links': {'overview': conversation_link(conversation.id)},
        } for conversation, role in rows],
        'links': {
            'self': self_link,
            'siteAdminDashboard': site_admin_link if site_admin else None,
        },
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
