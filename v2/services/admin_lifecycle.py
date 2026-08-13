"""Admin conversation lifecycle projection and guided transition command."""

from dataclasses import dataclass
from datetime import timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_admin_lifecycle(
    *, conversation, role_label: str, phase_sequence: list[dict],
    current_stage_index: int, active_phase_keys: set[str], linear: bool,
    transition: dict | None, schedule: dict, counts: dict,
    can_organize: bool, can_administer: bool, links: dict,
) -> dict:
    if conversation.closed_at:
        status = 'closed'
    elif conversation.paused:
        status = 'paused'
    elif schedule['scheduled_at'] and not schedule['frozen']:
        status = 'scheduled'
    else:
        status = 'active'
    if conversation.closed_at:
        publication = 'published'
    elif 'public_results' in active_phase_keys:
        publication = 'pending'
    else:
        publication = 'not_applicable'

    steps = []
    for index, stage in enumerate(phase_sequence):
        if linear:
            state = ('current' if index == current_stage_index
                     else 'completed' if index < current_stage_index
                     else 'upcoming')
        else:
            state = 'current' if stage['key'] in active_phase_keys else 'available'
        steps.append({
            'key': stage['key'], 'label': stage['label'],
            'effect': stage['effect'], 'state': state,
        })

    transition_dto = None
    if transition:
        transition_dto = {
            'source': {
                'key': transition['source']['key'],
                'label': transition['source']['label'],
            },
            'target': {
                'key': transition['target']['key'],
                'label': transition['target']['label'],
            },
            'consequence': transition['consequence'],
            'preconditions': [{
                'id': row['id'], 'label': row['label'],
                'met': row['met'], 'note': row['note'],
            } for row in transition['preconditions']],
            'requiresPhase6Initialization': transition['runs_phase6_init'],
        }

    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
            'accessPolicy': conversation.access_policy,
            'status': status,
            'publication': publication,
            'closedAt': _utc_iso(conversation.closed_at),
        },
        'operator': {'roleLabel': role_label},
        'phase': {
            'linear': linear,
            'currentIndex': current_stage_index,
            'activeKeys': sorted(active_phase_keys),
            'steps': steps,
            'transition': transition_dto,
        },
        'schedule': {
            'canSchedule': schedule['can_schedule'] and can_administer,
            'scheduledAt': _utc_iso(schedule['scheduled_at']),
            'targetKey': schedule['scheduled_target'],
            'targetLabel': schedule['scheduled_label'],
            'frozen': schedule['frozen'],
        },
        'counts': counts,
        'capabilities': {
            'advancePhase': can_organize and transition is not None,
            'pause': can_administer and bool(conversation.active),
            'publish': can_administer and publication == 'pending',
            'editSettings': can_organize,
            'useAdvancedPhases': can_administer,
        },
        'links': links,
    }


class PhaseTransitionUnavailable(RuntimeError):
    def __init__(self, *, nonlinear: bool):
        self.nonlinear = nonlinear


class PhaseReadinessUnconfirmed(ValueError):
    def __init__(self, ids: list[str]):
        self.ids = ids


class PhaseReadinessBlocked(RuntimeError):
    def __init__(self, ids: list[str]):
        self.ids = ids


class PhasePreparationFailed(RuntimeError):
    def __init__(self, message: str):
        self.message = message


class PhaseTransitionConflict(RuntimeError):
    def __init__(self, *, orphaned_phase6_id: str | None):
        self.orphaned_phase6_id = orphaned_phase6_id


class PhaseTransitionSaveFailed(RuntimeError):
    def __init__(self, *, outcome_unknown: bool, orphaned_phase6_id: str | None):
        self.outcome_unknown = outcome_unknown
        self.orphaned_phase6_id = orphaned_phase6_id


@dataclass(frozen=True)
class PhaseTransitionResult:
    source_key: str
    target_key: str
    target_label: str
    phase6_created: bool
    sync_message: str | None
    visibility_synced: bool


def advance_conversation_phase(
    *, conversation, transition: dict | None, linear: bool,
    confirmed_preconditions: set[str], session, init_phase6,
    sync_phase6, apply_transition, sync_visibility, invalidate_results,
    audit, logger,
) -> PhaseTransitionResult:
    """Execute the guided transition without holding a lock over upstream I/O."""
    if transition is None:
        raise PhaseTransitionUnavailable(nonlinear=not linear)
    required = [row['id'] for row in transition['preconditions']]
    missing = [key for key in required if key not in confirmed_preconditions]
    if missing:
        raise PhaseReadinessUnconfirmed(missing)
    blocked = [
        row['id'] for row in transition['preconditions']
        if row.get('met') is False
    ]
    if blocked:
        raise PhaseReadinessBlocked(blocked)

    created_phase6_id = None
    sync_message = None
    if transition['runs_phase6_init']:
        if not conversation.phase6_polis_conversation_id:
            ok, message = init_phase6(conversation)
            if not ok:
                session.rollback()
                raise PhasePreparationFailed(message)
            created_phase6_id = conversation.phase6_polis_conversation_id
        else:
            ok, sync_message = sync_phase6(conversation)
            if not ok:
                session.rollback()
                raise PhasePreparationFailed(sync_message)

    source_key, target_key = apply_transition(conversation, transition)
    slug = conversation.slug
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if created_phase6_id:
            logger.error(
                'Phase advance lost a concurrent race after Phase 6 init — '
                'orphaned Polis conversation %s (conv %s)',
                created_phase6_id, slug,
            )
        raise PhaseTransitionConflict(
            orphaned_phase6_id=created_phase6_id,
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        if created_phase6_id:
            logger.error(
                'Phase advance commit failed after Phase 6 init — '
                'orphaned Polis conversation %s (conv %s)',
                created_phase6_id, slug,
            )
        raise PhaseTransitionSaveFailed(
            outcome_unknown=bool(created_phase6_id),
            orphaned_phase6_id=created_phase6_id,
        ) from exc

    audit(
        'phase.advance', conv_id=conversation.id,
        target_type='phase', target_id=target_key,
        from_phase=source_key, phase6_created=bool(created_phase6_id),
    )
    visibility_synced = sync_visibility(conversation)
    invalidate_results(conversation)
    return PhaseTransitionResult(
        source_key=source_key,
        target_key=target_key,
        target_label=transition['target']['label'],
        phase6_created=bool(created_phase6_id),
        sync_message=sync_message,
        visibility_synced=visibility_synced,
    )
