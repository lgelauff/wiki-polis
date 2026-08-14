"""Phase 2 intermediate-results presentation contract tests."""

from services.intermediate_results import build_intermediate_results


class Conversation:
    slug = 'initial-round'
    title = 'Initial round'


def _build(results, stats=None, recomputing=False):
    return build_intermediate_results(
        conversation=Conversation(), results=results, polis_stats=stats,
        recomputing=recomputing, self_link='/self',
        conversation_link='/conversation', about_link='/about',
    )


def test_projects_consensus_groups_and_small_sample_without_upstream_ids():
    data = _build({
        'majority': {
            'agree': [{'statement_text': 'Shared maintenance', 'value': .829}],
            'disagree': [{'statement_text': 'Centralize everything', 'value': .64}],
        },
        'groups': [{
            'agree': [{'statement_text': 'Local autonomy', 'value': .765}],
            'disagree': [],
            'id': 'private-group-id',
        }],
    }, {'n_participants': 12, 'n_votes': 40})

    assert data['state'] == 'ready'
    assert data['participantCount'] == 12
    assert data['smallSample'] is True
    assert data['consensus'] == [
        {'choice': 'agree', 'statement': 'Shared maintenance', 'percentage': 82},
        {'choice': 'disagree', 'statement': 'Centralize everything', 'percentage': 64},
    ]
    assert data['groups'] == [{
        'label': 'Group 1',
        'positions': [
            {'choice': 'agree', 'statement': 'Local autonomy', 'percentage': 76},
        ],
    }]
    assert 'private-group-id' not in str(data)


def test_distinguishes_recomputing_pending_and_unknown_sample_size():
    assert _build(None, recomputing=True)['state'] == 'recomputing'
    pending = _build(None)
    assert pending['state'] == 'pending'
    assert pending['participantCount'] is None
    assert pending['smallSample'] is False
