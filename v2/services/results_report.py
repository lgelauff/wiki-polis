"""Privacy-safe participant results/report projection."""

from datetime import timezone


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _tally(value: dict | None) -> dict | None:
    if value is None:
        return None
    return {
        'counts': {
            'agree': int(value.get('n_agree') or 0),
            'pass': int(value.get('n_pass') or 0),
            'disagree': int(value.get('n_disagree') or 0),
            'voters': int(value.get('n_voters') or 0),
        },
        'percentages': {
            'agree': float(value.get('pct_agree') or 0),
            'pass': float(value.get('pct_pass') or 0),
            'disagree': float(value.get('pct_disagree') or 0),
        },
    }


def _opinion_groups(groups: list | None) -> list[dict]:
    projected = []
    for index, group in enumerate(groups or [], start=1):
        positions = []
        for choice in ('agree', 'disagree'):
            for item in group.get(choice, []) or []:
                text = str(item.get('statement_text') or '').strip()
                if not text:
                    continue
                raw_value = item.get('value')
                positions.append({
                    'choice': choice,
                    'statement': text,
                    'percentage': (
                        round(float(raw_value) * 100, 1)
                        if isinstance(raw_value, (int, float)) else None
                    ),
                })
        projected.append({
            'label': f'Group {index}',
            'memberCount': (
                int(group['n_members'])
                if isinstance(group.get('n_members'), int) else None
            ),
            'positions': positions,
        })
    return projected


def build_results_report(
    *, conversation, phase6_results: dict | None, output_context: dict,
    participation, reveal_state: str | None,
    self_link: str, conversation_link: str, about_link: str,
    identity_reveal_link: str | None,
) -> dict:
    results = phase6_results or {}
    detailed = bool(results.get('pg_available'))
    statements = []
    for row in results.get('statements', []):
        statements.append({
            'featuredStatementId': row['fs_id'],
            'statement': row['text'],
            'initial': _tally(row.get('p2')) if detailed else None,
            'informed': _tally(row.get('p6')) if detailed else None,
            'agreementShift': row.get('shift') if detailed else None,
        })
    result_filter = results.get('filter')
    links = {
        'self': self_link,
        'conversation': conversation_link,
        'about': about_link,
    }
    if identity_reveal_link:
        links['identityReveal'] = identity_reveal_link
    return {
        'slug': conversation.slug,
        'title': conversation.title,
        'publication': 'final' if conversation.closed_at else 'preliminary',
        'resultsAvailable': phase6_results is not None,
        'openedAt': _utc_iso(conversation.created_at),
        'closedAt': _utc_iso(conversation.closed_at),
        'context': {
            'phase': output_context['phase'],
            'status': output_context['status'],
            'method': output_context['method'],
        },
        'participation': {
            'initialRound': results.get('p2_participants'),
            'informedRound': results.get('p6_participants'),
            'matchedRounds': results.get('matched_participants'),
        },
        'dataAvailability': {
            'detailedCounts': detailed,
            'opinionGroups': bool(results.get('clusters')),
        },
        'moderation': {
            'excludedStatements': len(result_filter.excluded_tids) if result_filter else 0,
            'excludedParticipants': len(result_filter.excluded_pids) if result_filter else 0,
        },
        'statements': statements,
        'opinionGroups': _opinion_groups(results.get('clusters')),
        'viewer': {
            'participating': participation is not None,
            'pseudonym': participation.pseudonym if participation else None,
            'revealState': reveal_state,
        },
        'links': links,
    }
