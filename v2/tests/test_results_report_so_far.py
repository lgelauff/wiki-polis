"""The site-admin report preview before the informed opinion round (#598).

Before Phase 6 has results, the preview shows the Explore round's tallies for the featured
statements once Explore is over, and their arguments once the Arguments phase is over; the
informed-round sections know that round is missing. None of this reaches the public
results route, which has no audience gate for it yet (#568).
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app import _current_phase6_results_filter
from tests.test_results_report_api import _results
from db import Argument, ArgumentVote, FeaturedStatement, Participant, db


def _url(conversation):
    return f'/api/v1/admin/conversations/{conversation.id}/report-preview'


def _server(*, counts, hidden=(), participants=30):
    """A Polis stats client: Explore counts per tid, and the hidden Explore statements."""
    server = MagicMock()
    server.get_phase6_vote_counts.side_effect = (
        lambda _zinvite, tids, _pids: {tid: counts[tid] for tid in tids if tid in counts}
    )
    server.get_phase6_participant_count.return_value = participants
    server.get_statements.return_value = (
        [], [], [{'tid': tid, 'txt': 'hidden'} for tid in hidden],
    )
    return server


def _counts(agree, disagree, pass_):
    return {'n_agree': agree, 'n_disagree': disagree, 'n_pass': pass_,
            'n_voters': agree + disagree + pass_}


def _featured(conversation):
    """Three confirmed featured statements (Explore tids 1-3), one unconfirmed (tid 4)."""
    rows = [
        FeaturedStatement(conversation_id=conversation.id, polis_statement_id=tid,
                          statement_text=f'Statement {tid}', confirmed_by_admin=tid != 4)
        for tid in (1, 2, 3, 4)
    ]
    db.session.add_all(rows)
    db.session.commit()
    return rows


def _voters(count):
    people = [Participant(mw_user_id=1000 + i, mw_username=f'voter{i}', xid=f'xid-{i}')
              for i in range(count)]
    db.session.add_all(people)
    db.session.commit()
    return people


def _after_arguments(conversation):
    """Explore and Arguments are over: the process is in the cleanup pause."""
    conversation.phase_submission = False
    conversation.phase_argument_mapping = False
    conversation.phase_cleanup = True
    db.session.commit()


def _with_arguments(featured):
    voters = _voters(2)
    strong = Argument(featured_statement_id=featured.id, proposer_pseudonym='calm-heron',
                      side='pro', body='Strong reason for')
    db.session.add(strong)
    db.session.flush()
    db.session.add_all([ArgumentVote(argument_id=strong.id, participant_id=p.id)
                        for p in voters])
    db.session.commit()


def test_preview_before_the_informed_round_shows_the_explore_round(
    admin_client, conversation,
):
    _after_arguments(conversation)
    one, two, three, _ = _featured(conversation)
    voters = _voters(2)
    strong = Argument(featured_statement_id=one.id, proposer_pseudonym='calm-heron',
                      side='pro', body='Strong reason for')
    weak = Argument(featured_statement_id=one.id, proposer_pseudonym='brave-lynx',
                    side='pro', body='Weak reason for')
    hidden = Argument(featured_statement_id=one.id, proposer_pseudonym='odd-newt',
                      side='con', body='Hidden reason against', hidden=True)
    against = Argument(featured_statement_id=one.id, proposer_pseudonym=None,
                       side='con', body='Reason against')
    db.session.add_all([weak, strong, hidden, against])
    db.session.flush()
    db.session.add_all([ArgumentVote(argument_id=strong.id, participant_id=p.id)
                        for p in voters])
    db.session.commit()
    server = _server(
        counts={1: _counts(12, 5, 3), 2: _counts(4, 2, 1)},  # tid 2 is below the floor
        hidden={3},
    )

    with patch('app._polis_server_client', return_value=server):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['resultsAvailable'] is True
    assert data['dataAvailability']['informedRound'] == 'pending'
    assert data['context']['sources'] == ['submission', 'argument_mapping']
    assert data['participation'] == {'initialRound': 30, 'informedRound': None,
                                     'matchedRounds': None}
    # The hidden Explore statement (tid 3) and the unconfirmed one (tid 4) are not reported.
    assert data['moderation']['excludedStatements'] == 1
    rows = {row['featuredStatementId']: row for row in data['statements']}
    assert set(rows) == {one.id, two.id}
    assert rows[one.id]['initial']['percentages'] == {'agree': 60, 'pass': 15, 'disagree': 25}
    assert rows[one.id]['initial']['counts']['voters'] == 20
    # Below the floor nothing is shown, not even a count.
    assert rows[two.id]['initial'] == {'counts': None, 'percentages': None, 'belowFloor': True}
    for row in rows.values():
        assert row['informed'] is None
        assert row['agreementShift'] is None
        # Per-statement totals only: nothing about how any one person voted.
        assert row['viewerChoice'] is None
        assert row['viewerGroupChoice'] is None
        assert row['personalDelta'] is None
    assert data['viewer'] == {'participating': False, 'pseudonym': None, 'revealState': None}
    assert data['opinionGroups'] == []
    # Most supported first; hidden arguments never; text only.
    assert rows[one.id]['arguments'] == {
        'for': ['Strong reason for', 'Weak reason for'], 'against': ['Reason against'],
    }
    assert rows[two.id]['arguments'] == {'for': [], 'against': []}
    serialized = json.dumps(data)
    for name in ('calm-heron', 'brave-lynx', 'odd-newt', 'Hidden reason against', 'voter0'):
        assert name not in serialized
    assert conversation.polis_id not in serialized
    # The moderation filter was read from the Explore round, the round the page uses.
    server.get_statements.assert_called_with(conversation.polis_id)


def test_preview_while_explore_is_open_shows_no_results(admin_client, conversation):
    conversation.phase_submission = True
    db.session.commit()
    _featured(conversation)
    server = _server(counts={1: _counts(12, 5, 3)})

    with patch('app._polis_server_client', return_value=server):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['resultsAvailable'] is False
    assert data['statements'] == []
    server.get_phase6_vote_counts.assert_not_called()


def test_preview_while_arguments_are_open_leaves_them_out(admin_client, conversation):
    conversation.phase_argument_mapping = True
    db.session.commit()
    one = _featured(conversation)[0]
    _with_arguments(one)

    with patch('app._polis_server_client',
               return_value=_server(counts={1: _counts(12, 5, 3)})):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['resultsAvailable'] is True
    assert data['context']['sources'] == ['submission']
    assert all(row['arguments'] == {'for': [], 'against': []} for row in data['statements'])
    assert 'Strong reason for' not in json.dumps(data)


def test_preview_without_featured_statements_still_has_no_results(admin_client, conversation):
    _after_arguments(conversation)
    with patch('app._polis_server_client', return_value=_server(counts={})):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['resultsAvailable'] is False
    assert data['statements'] == []
    assert data['context']['sources'] == []


def test_explore_results_degrade_without_the_results_database(admin_client, conversation):
    _after_arguments(conversation)
    _featured(conversation)
    server = _server(counts={})
    server.get_phase6_vote_counts.side_effect = None
    server.get_phase6_vote_counts.return_value = None
    server.get_statements.return_value = None

    with patch('app._polis_server_client', return_value=server):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['resultsAvailable'] is True
    assert data['dataAvailability']['detailedCounts'] is False
    assert all(row['initial'] is None for row in data['statements'])


def test_a_route_without_the_informed_round_skips_it(admin_client, conversation):
    conversation.phase_route = 'no_informed_vote'
    _after_arguments(conversation)
    _featured(conversation)

    with patch('app._polis_server_client',
               return_value=_server(counts={1: _counts(12, 5, 3)})):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['dataAvailability']['informedRound'] == 'skipped'
    assert data['context']['sources'] == ['submission']


# The public results payload's keys before #598; the preview adds to them, nothing else does.
_PUBLIC_CONTEXT = {'phase', 'status', 'method'}
_PUBLIC_AVAILABILITY = {'detailedCounts', 'opinionGroups', 'personalLens', 'responseFloor'}
_PUBLIC_STATEMENT = {
    'featuredStatementId', 'statement', 'initial', 'informed', 'agreementShift',
    'viewerChoice', 'viewerGroupChoice', 'viewerMatchesGroup', 'personalDelta',
}


def _assert_public_shape(data):
    assert set(data['context']) == _PUBLIC_CONTEXT
    assert set(data['dataAvailability']) == _PUBLIC_AVAILABILITY
    for row in data['statements']:
        assert set(row) == _PUBLIC_STATEMENT


def test_public_report_without_the_informed_round_is_unchanged(client, conversation):
    """No Explore fallback and no arguments on /results, even for a closed process that
    the preview would show results for: that route has no audience gate yet (#568)."""
    conversation.phase_route = 'no_informed_vote'
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    _with_arguments(_featured(conversation)[0])
    server = _server(counts={1: _counts(12, 5, 3)})

    with patch('app._polis_server_client', return_value=server):
        data = client.get('/api/v1/conversations/test-conv/results').get_json()['data']

    assert data['resultsAvailable'] is False
    assert data['statements'] == []
    _assert_public_shape(data)
    assert 'Statement 1' not in json.dumps(data)
    server.get_phase6_vote_counts.assert_not_called()


def test_open_preliminary_results_are_unchanged(client, conversation):
    conversation.phase_public_results = True
    db.session.commit()
    _with_arguments(_featured(conversation)[0])

    with patch('app._polis_server_client',
               return_value=_server(counts={1: _counts(12, 5, 3)})):
        data = client.get('/api/v1/conversations/test-conv/results').get_json()['data']

    assert data['publication'] == 'preliminary'
    assert data['resultsAvailable'] is False
    _assert_public_shape(data)


def test_public_report_with_the_informed_round_carries_no_arguments(client, conversation):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()
    featured = _featured(conversation)[0]
    _with_arguments(featured)
    results = _results()
    results['statements'][0]['fs_id'] = featured.id

    with patch('app._build_phase6_results', return_value=results):
        data = client.get('/api/v1/conversations/test-conv/results').get_json()['data']

    assert data['resultsAvailable'] is True
    _assert_public_shape(data)
    assert 'Strong reason for' not in json.dumps(data)


def test_public_report_filter_is_still_the_informed_round_alone(app, conversation):
    server = _server(counts={}, hidden={5})
    with patch('app._polis_server_client', return_value=server):
        assert _current_phase6_results_filter(conversation).excluded_tids == frozenset()
    server.get_statements.assert_not_called()


def test_preview_with_the_informed_round_includes_it(admin_client, conversation):
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()

    with patch('app._build_phase6_results', return_value=_results()):
        data = admin_client.get(_url(conversation)).get_json()['data']

    assert data['dataAvailability']['informedRound'] == 'included'
    assert data['context']['sources'] == ['submission', 'informed_voting']
