"""Participant workspace presentation contract shared by HTML and SPA adapters."""

from datetime import timezone

from services.conversation_lanes import participant_can_act, scheduled_transition


TAB_LABELS = {
    'vote': 'Vote',
    'results': 'Intermediate results',
    'arguments': 'Arguments',
    'informed-voting': 'Informed vote',
    'p6-results': 'Preliminary results',
}


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _reveal_projection(reveal: dict | None, pseudonym: str | None) -> dict | None:
    if reveal is None:
        return None
    return {
        'state': reveal['state'],
        'pseudonym': pseudonym,
        'closedAt': _utc_iso(reveal['closed_at']),
        'opensAt': _utc_iso(reveal['opens_at']),
        'closesAt': _utc_iso(reveal['closes_at']),
        'daysRemaining': int(reveal['days_left']),
    }


def build_conversation_workspace(
    *, conversation, participation, can_moderate: bool,
    space_warning: str | None, reveal: dict | None,
    phase6_results_available: bool, links: dict,
) -> dict:
    """Project the page-level state without duplicating phase payloads.

    The phase-specific APIs remain authoritative for voting, arguments and results.
    This projection owns only the composition decisions previously embedded in
    ``conversation.html``.
    """
    status = (
        'closed' if not conversation.active else
        'paused' if conversation.paused else
        'open'
    )
    tab_keys = []
    if status == 'open':
        if conversation.phase_submission:
            tab_keys.append('vote')
        if conversation.phase_personal_results or conversation.phase_public_results:
            tab_keys.append('results')
        if conversation.phase_argument_mapping:
            tab_keys.append('arguments')
        if (conversation.phase_informed_voting
                and conversation.phase6_polis_conversation_id):
            tab_keys.append('informed-voting')
        if conversation.phase_public_results and phase6_results_available:
            tab_keys.append('p6-results')

    phases = {
        'vote': 'explore',
        'results': 'intermediateResults',
        'arguments': 'arguments',
        'informed-voting': 'informedVoting',
        'p6-results': 'results',
    }
    tabs = [
        {
            'key': key,
            'label': TAB_LABELS[key],
            'dataHref': links.get(phases.get(key, '')),
        }
        for key in tab_keys
    ]
    config = conversation.argument_vote_data or {}
    joined = participation is not None
    action_phases = {
        key for key, enabled in (
            ('submission', conversation.phase_submission),
            ('argument_mapping', conversation.phase_argument_mapping),
            ('informed_voting', conversation.phase_informed_voting),
        ) if enabled
    }
    return {
        'slug': conversation.slug,
        'title': conversation.title,
        'space': 'demo' if conversation.access_policy == 'demo' else 'real',
        'status': status,
        'descriptionHtml': conversation.intro_text,
        'outroHtml': conversation.outro_text,
        'viewer': {
            'state': 'participant' if joined else 'join_required',
            'pseudonym': participation.pseudonym if joined else None,
        },
        'spaceWarning': space_warning,
        'scheduledTransition': scheduled_transition(conversation),
        'tabs': tabs,
        'defaultTab': tab_keys[0] if tab_keys else None,
        'reveal': _reveal_projection(
            reveal, participation.pseudonym if participation else None,
        ),
        'statementContribution': {
            'unlockAfter': int(config.get('new_stmt_unlock_at', 10)),
            'quota': int(config.get('new_stmt_max', 3)),
            'used': len(participation.new_stmt_ids or []) if participation else 0,
        },
        'capabilities': {
            'participate': joined and participant_can_act(
                active=conversation.active,
                paused=conversation.paused,
                phases=action_phases,
            ),
            'moderate': can_moderate,
        },
        'links': links,
    }
