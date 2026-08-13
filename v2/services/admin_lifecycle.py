"""Admin conversation lifecycle projection."""

from datetime import timezone


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
