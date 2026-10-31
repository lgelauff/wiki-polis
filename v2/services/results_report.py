"""Privacy-safe participant results/report projection."""

from datetime import timezone

from services import reporting_rules


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _tally(value: dict | None, *, exact_counts: bool) -> dict | None:
    """Floor, round and (for the public) drop the counts; see services.reporting_rules."""
    return reporting_rules.tally(value, exact_counts=exact_counts)


def _agreement_shift(row: dict) -> int | None:
    """The P2 -> P6 shift, from the counts here rather than trusted from the row: withheld
    unless both rounds pass the floor, so it never outlives a withheld tally."""
    initial, informed = row.get('p2'), row.get('p6')
    if not initial or not informed:
        return None
    return reporting_rules.shift(
        int(initial.get('n_agree') or 0), int(initial.get('n_voters') or 0),
        int(informed.get('n_agree') or 0), int(informed.get('n_voters') or 0),
    )


def _choice(vote: int | None) -> str | None:
    """The viewer's own vote as a stable identifier, from the raw Polis value.

    Polis encodes -1 = Agree, 1 = Disagree, 0 = Pass in the vote table and API (the data
    export inverts the sign -- see ref_polis-data-model.md). This previously parsed the
    English label instead, which silently returned None for every vote once the labels
    read "Agreed"/"Disagreed"/"Passed": none of those match the identifiers below. The
    SPA translates the identifier, so no display text crosses the API for it.
    """
    return {-1: 'agree', 1: 'disagree', 0: 'pass'}.get(vote) if vote is not None else None


def _group_choice(votes: dict | None) -> str | None:
    """Return the group's clear agree/disagree position; ties and all-pass are neutral."""
    if not votes:
        return None
    agree = int(votes.get('n_agree') or 0)
    disagree = int(votes.get('n_disagree') or 0)
    if agree == disagree:
        return None
    return 'agree' if agree > disagree else 'disagree'


def _personal_delta(row: dict) -> dict | None:
    initial = _choice(row.get('my_p2_vote'))
    informed = _choice(row.get('my_p6_vote'))
    if initial is None or informed is None:
        return None
    return {
        'initial': initial,
        'informed': informed,
        'changed': initial != informed,
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



class ReportPublished(RuntimeError):
    """A preview was asked for after publication; the published report replaces it."""

    def __init__(self, report_link: str):
        super().__init__('The report is already published.')
        self.report_link = report_link

def build_results_report(
    *, conversation, phase6_results: dict | None, output_context: dict,
    participation, reveal_state: str | None,
    self_link: str, conversation_link: str, about_link: str,
    identity_reveal_link: str | None,
    full_view: bool,
    preview: bool = False,
) -> dict:
    """Build the results report. ``preview`` marks a site-admin preview, never published.

    ``full_view`` is for participants of the process, its organizers and site admins: exact
    counts and opinion groups. Everyone else gets the public view (decision 4, D8):
    percentages only, no groups. Neither view carries numbers below the floor.
    """
    results = phase6_results or {}
    detailed = bool(results.get('pg_available'))
    # The published report's full shape (cross-round comparison, opinion groups). A site
    # admin's preview shows that shape too, so it looks as the report would if published now.
    report_shape = bool(conversation.closed_at) or preview
    personal_lens = bool(
        not report_shape and participation and results.get('personal_lens_available')
    )
    statements = []
    for row in results.get('statements', []):
        # A participant's own choice in a results table is part of the personal lens
        # (owner, 2026-10-17), which stays off until its privacy gate (#233) is defined.
        viewer_choice = _choice(row.get('my_p6_vote')) if personal_lens else None
        group_choice = _group_choice(row.get('my_group_votes')) if personal_lens else None
        statements.append({
            'featuredStatementId': row['fs_id'],
            'statement': row['text'],
            # Cross-round aggregate comparison belongs to the published Report only.
            'initial': (
                _tally(row.get('p2'), exact_counts=full_view)
                if detailed and report_shape else None
            ),
            'informed': _tally(row.get('p6'), exact_counts=full_view) if detailed else None,
            'agreementShift': _agreement_shift(row) if detailed and report_shape else None,
            # A participant's own round delta and group comparison stay private and live.
            'viewerChoice': viewer_choice,
            'viewerGroupChoice': group_choice,
            'viewerMatchesGroup': (
                viewer_choice == group_choice
                if viewer_choice is not None and group_choice is not None else None
            ),
            'personalDelta': _personal_delta(row) if personal_lens else None,
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
        'publication': (
            'preview' if preview
            else 'final' if report_shape else 'preliminary'
        ),
        'resultsAvailable': phase6_results is not None,
        'openedAt': _utc_iso(conversation.created_at),
        'closedAt': _utc_iso(conversation.closed_at),
        'context': {
            'phase': output_context['phase'],
            # A preview uses the report's output definition but is not final.
            'status': 'provisional' if preview else output_context['status'],
            'method': output_context['method'],
        },
        'participation': {
            # Preliminary results are a single-round surface, not a partial Report.
            'initialRound': results.get('p2_participants') if report_shape else None,
            'informedRound': results.get('p6_participants'),
            'matchedRounds': results.get('matched_participants') if report_shape else None,
        },
        'dataAvailability': {
            'detailedCounts': detailed,
            'opinionGroups': bool(report_shape and full_view and results.get('clusters')),
            'personalLens': personal_lens,
            'responseFloor': reporting_rules.min_total(),
        },
        'moderation': {
            'excludedStatements': len(result_filter.excluded_tids) if result_filter else 0,
            'excludedParticipants': len(result_filter.excluded_pids) if result_filter else 0,
        },
        'statements': statements,
        'opinionGroups': (
            _opinion_groups(results.get('clusters')) if report_shape and full_view else []
        ),
        'viewer': {
            'participating': participation is not None,
            'pseudonym': participation.pseudonym if participation else None,
            'revealState': reveal_state,
        },
        'links': links,
    }
