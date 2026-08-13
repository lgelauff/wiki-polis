"""Conversation-role roster projection and set-replacement command."""

from dataclasses import dataclass
from datetime import timezone

from db import ADMIN_ROLES, AdminRole, Conversation, Participant, db


def _utc_iso(value) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_admin_role_roster(
    *, conversation: Conversation, can_manage: bool,
    self_link: str, conversation_link: str,
) -> dict:
    roles = (
        AdminRole.query
        .filter_by(conversation_id=conversation.id)
        .join(Participant, AdminRole.participant_id == Participant.id)
        .order_by(Participant.mw_username, AdminRole.role)
        .all()
    )
    by_participant = {}
    for role in roles:
        row = by_participant.setdefault(role.participant_id, {
            'participantId': role.participant_id,
            'username': role.participant.mw_username,
            'roles': [],
            'grantedAt': [],
        })
        row['roles'].append(role.role)
        row['grantedAt'].append(_utc_iso(role.granted_at))
    candidates = []
    if can_manage:
        candidates = [{
            'participantId': participant.id,
            'username': participant.mw_username,
        } for participant in Participant.query.order_by(Participant.mw_username).all()]
    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
        },
        'assignments': list(by_participant.values()),
        'candidates': candidates,
        'availableRoles': list(ADMIN_ROLES),
        'capabilities': {'manageRoles': can_manage},
        'links': {'self': self_link, 'conversation': conversation_link},
    }


class RoleParticipantNotFound(LookupError):
    pass


@dataclass(frozen=True)
class RoleSetResult:
    participant: Participant
    roles: list[str]
    added: list[str]
    removed: list[str]


def replace_conversation_roles(
    *, conversation: Conversation, participant_id: int,
    roles: list[str], grantor: Participant | None, audit,
) -> RoleSetResult:
    participant = (
        Participant.query.filter_by(id=participant_id).with_for_update().first()
    )
    if participant is None:
        raise RoleParticipantNotFound()
    desired = set(roles)
    current_rows = AdminRole.query.filter_by(
        conversation_id=conversation.id, participant_id=participant.id,
    ).all()
    current = {row.role for row in current_rows}
    added = sorted(desired - current)
    removed = sorted(current - desired)
    for row in current_rows:
        if row.role in removed:
            db.session.delete(row)
    for role in added:
        db.session.add(AdminRole(
            participant_id=participant.id,
            conversation_id=conversation.id,
            role=role,
            granted_by=grantor.id if grantor else None,
        ))
    db.session.commit()
    for role in removed:
        audit(
            'role.revoke', conv_id=conversation.id,
            target_type='participant', target_id=participant.id, role=role,
        )
    for role in added:
        audit(
            'role.grant', conv_id=conversation.id,
            target_type='participant', target_id=participant.id, role=role,
        )
    return RoleSetResult(
        participant=participant,
        roles=sorted(desired),
        added=added,
        removed=removed,
    )
