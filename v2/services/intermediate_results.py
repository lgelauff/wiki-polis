"""Participant-safe Phase 2 clustering presentation contract."""


def _positions(items: list | None, choice: str) -> list[dict]:
    projected = []
    for item in items or []:
        statement = str(item.get('statement_text') or '').strip()
        value = item.get('value')
        if not statement or not isinstance(value, (int, float)):
            continue
        projected.append({
            'choice': choice,
            'statement': statement,
            'percentage': int(float(value) * 100),
        })
    return projected


def build_intermediate_results(
    *, conversation, results: dict | None, polis_stats: dict | None,
    recomputing: bool, self_link: str, conversation_link: str,
    about_link: str,
) -> dict:
    """Project the live initial-round results without upstream identifiers."""
    majority = (results or {}).get('majority') or {}
    consensus = (
        _positions(majority.get('agree'), 'agree')
        + _positions(majority.get('disagree'), 'disagree')
    )
    groups = []
    for index, group in enumerate((results or {}).get('groups') or [], start=1):
        groups.append({
            'label': f'Group {index}',
            'positions': (
                _positions(group.get('agree'), 'agree')
                + _positions(group.get('disagree'), 'disagree')
            ),
        })
    participant_count = (
        int(polis_stats['n_participants'])
        if polis_stats and isinstance(polis_stats.get('n_participants'), int)
        else None
    )
    state = 'ready' if results else 'recomputing' if recomputing else 'pending'
    return {
        'slug': conversation.slug,
        'title': conversation.title,
        'state': state,
        'participantCount': participant_count,
        'smallSample': bool(
            results and participant_count is not None and participant_count < 25
        ),
        'consensus': consensus,
        'groups': groups,
        'links': {
            'self': self_link,
            'conversation': conversation_link,
            'about': about_link,
        },
    }
