"""Privacy-safe preliminary/final results API contract tests."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app import Phase6ResultsFilter
from db import FeaturedStatement, Participation, db


def _results(*, pg_available=True):
    return {
        'statements': [{
            'fs_id': 8,
            'text': 'Communities should share infrastructure.',
            'p2': {
                'n_agree': 12, 'n_pass': 3, 'n_disagree': 5, 'n_voters': 20,
                'pct_agree': 60.0, 'pct_pass': 15.0, 'pct_disagree': 25.0,
            },
            'p6': {
                'n_agree': 14, 'n_pass': 4, 'n_disagree': 2, 'n_voters': 20,
                'pct_agree': 70.0, 'pct_pass': 20.0, 'pct_disagree': 10.0,
            },
            'shift': 10.0,
            'my_p6_vote': -1,          # raw Polis value: -1 = Agree
        }],
        'p2_participants': 25,
        'p6_participants': 22,
        'matched_participants': None,
        'filter': Phase6ResultsFilter(
            excluded_tids=frozenset({42}), excluded_pids=frozenset({7, 9}),
        ),
        'clusters': [{
            'n_members': 11,
            'agree': [{'statement_text': 'Shared maintenance matters', 'value': .82}],
            'disagree': [{'statement_text': 'Centralize every budget', 'value': .64}],
        }],
        'pg_available': pg_available,
    }


def test_final_results_api_uses_snapshot_and_preserves_pass_tallies(
    client, conversation,
):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    conversation.report_filter_snapshot = {
        'excluded_tids': [42], 'excluded_pids': [7, 9],
    }
    db.session.commit()
    seen = {}

    def build(_conversation, participation, results_filter=None):
        seen['participation'] = participation
        seen['filter'] = results_filter
        return _results()

    with patch('app._build_phase6_results', side_effect=build):
        response = client.get('/api/v1/conversations/test-conv/results')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['publication'] == 'final'
    assert data['resultsAvailable'] is True
    assert data['context']['status'] == 'final'
    assert data['moderation'] == {
        'excludedStatements': 1, 'excludedParticipants': 2,
    }
    assert data['statements'][0]['initial']['counts'] == {
        'agree': 12, 'pass': 3, 'disagree': 5, 'voters': 20,
    }
    assert data['statements'][0]['informed']['percentages'] == {
        'agree': 70.0, 'pass': 20.0, 'disagree': 10.0,
    }
    assert data['statements'][0]['agreementShift'] == 10.0
    assert data['statements'][0]['viewerChoice'] is None
    assert data['opinionGroups'][0] == {
        'label': 'Group 1',
        'memberCount': 11,
        'positions': [
            {'choice': 'agree', 'statement': 'Shared maintenance matters',
             'percentage': 82.0},
            {'choice': 'disagree', 'statement': 'Centralize every budget',
             'percentage': 64.0},
        ],
    }
    assert data['viewer'] == {
        'participating': False, 'pseudonym': None, 'revealState': 'pending',
    }
    assert seen['participation'] is None
    assert seen['filter'] == Phase6ResultsFilter(
        excluded_tids=frozenset({42}), excluded_pids=frozenset({7, 9}),
    )
    serialized = json.dumps(data)
    assert conversation.polis_id not in serialized
    assert conversation.phase6_polis_conversation_id not in serialized


def test_results_api_does_not_turn_database_outage_into_zero_tallies(
    client, conversation,
):
    conversation.phase_public_results = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()

    with patch('app._build_phase6_results', return_value=_results(pg_available=False)):
        data = client.get('/api/v1/conversations/test-conv/results').get_json()['data']

    assert data['publication'] == 'preliminary'
    assert data['dataAvailability']['detailedCounts'] is False
    assert data['statements'][0]['initial'] is None
    assert data['statements'][0]['informed'] is None
    assert data['statements'][0]['agreementShift'] is None


def test_results_api_rejects_unpublished_results(client, conversation):
    response = client.get('/api/v1/conversations/test-conv/results')

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'conflict'


def test_results_api_exposes_privacy_safe_viewer_report_state(
    auth_client, conversation, participant,
):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='curious-fox',
    ))
    db.session.commit()

    with (
        patch('app._build_phase6_results', return_value=None),
        patch('app._reveal_context', return_value={'state': 'open'}),
    ):
        data = auth_client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    assert data['resultsAvailable'] is False
    assert data['viewer'] == {
        'participating': True,
        'pseudonym': 'curious-fox',
        'revealState': 'open',
    }
    assert data['links']['identityReveal'] == '/c/test-conv/reveal'


def test_preliminary_results_passes_participation_for_private_vote_overlay(
    auth_client, conversation, participant,
):
    conversation.phase_public_results = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='reflective-fox',
    )
    db.session.add(participation)
    db.session.commit()
    seen = {}

    def build(_conversation, participation=None, results_filter=None):
        seen['participation'] = participation
        return _results()

    with patch('app._build_phase6_results', side_effect=build):
        data = auth_client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    assert seen['participation'].id == participation.id
    # The own choice in a results table waits for the personal lens (owner, 2026-10-17).
    assert data['statements'][0]['viewerChoice'] is None


def test_openapi_documents_results_report_and_pass_counts(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/conversations/{slug}/results']['get']
    counts = spec['components']['schemas']['VoteTally']['properties']['counts']

    assert operation['operationId'] == 'getResultsReport'
    assert 'pass' in counts['required']
    assert 'pass' in counts['properties']
    report_schema = spec['components']['schemas']['ResultsReport']
    availability = report_schema['properties']['dataAvailability']
    assert 'personalLens' in availability['required']
    assert 'personalLens' in availability['properties']
    statement_schema = spec['components']['schemas']['ResultsStatement']
    assert {'viewerGroupChoice', 'viewerMatchesGroup', 'personalDelta'} <= set(statement_schema['required'])
    assert spec['components']['schemas']['PersonalDelta']['required'] == [
        'initial', 'informed', 'changed',
    ]


def test_viewer_choice_maps_every_raw_polis_vote():
    """Guards the bug this fixture used to hide.

    `_build_phase6_results` emits the raw Polis vote; `_choice` used to parse an English
    label instead and returned None for every real vote, so the "Yours" column rendered
    an em dash for every statement. The fixture above hand-wrote 'Agree', a value the
    producer never emits, so the suite agreed with itself. Pin the whole mapping.
    """
    from services.results_report import _choice

    # ref_polis-data-model.md:147 -- the vote table and API use -1 = Agree, 1 = Disagree,
    # 0 = Pass. The data export inverts the sign; this is not the export.
    assert _choice(-1) == 'agree'
    assert _choice(1) == 'disagree'
    assert _choice(0) == 'pass'
    assert _choice(None) is None
    # Identifiers, never display text: the SPA translates these.
    assert {_choice(v) for v in (-1, 1, 0)} == {'agree', 'disagree', 'pass'}


def test_row_keys_the_report_reads_are_keys_the_producer_emits():
    """Tie the two halves of the row contract together statically.

    Every test in this file patches `_build_phase6_results` and hand-writes its rows, so
    nothing otherwise connects the keys the producer emits to the keys the consumer reads.
    That gap is what hid the original bug: the fixture said 'my_p6_label': 'Agree', a value
    the producer never emitted, and `_choice` silently returned None for every real vote.
    Rename a row key today and the whole suite stays green while viewerChoice reverts to
    always-null -- so check the contract itself rather than a fixture's idea of it.
    """
    import ast
    import pathlib

    v2 = pathlib.Path(__file__).resolve().parent.parent

    # Producer: the keys of the dict literal appended inside _build_phase6_results.
    producer = ast.parse((v2 / 'app.py').read_text(encoding='utf-8'))
    emitted: set[str] = set()
    for node in ast.walk(producer):
        if isinstance(node, ast.FunctionDef) and node.name == '_build_phase6_results':
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    emitted |= {
                        k.value for k in inner.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
    assert 'my_p6_vote' in emitted, (
        'guard is looking in the wrong place: _build_phase6_results no longer emits a dict '
        'literal containing my_p6_vote'
    )

    # Consumer: every row.get('...') in build_results_report.
    consumer = ast.parse((v2 / 'services' / 'results_report.py').read_text(encoding='utf-8'))
    read: set[str] = set()
    for node in ast.walk(consumer):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'get'
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'row'
                and node.args and isinstance(node.args[0], ast.Constant)):
            read.add(node.args[0].value)
    assert read, 'guard found no row.get(...) call sites in results_report.py'

    missing = sorted(read - emitted)
    assert not missing, (
        'results_report reads row keys that _build_phase6_results does not emit — '
        f'viewerChoice and friends will silently be None: {missing}'
    )


def test_preliminary_results_exposes_only_the_informed_round_publicly(
    client, conversation,
):
    conversation.phase_public_results = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.commit()

    with patch('app._build_phase6_results', return_value=_results()):
        data = client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    statement = data['statements'][0]
    assert statement['initial'] is None
    assert statement['informed']['counts']['voters'] == 20
    assert statement['agreementShift'] is None
    assert data['participation']['initialRound'] is None
    assert data['participation']['informedRound'] == 22
    assert data['participation']['matchedRounds'] is None
    assert data['dataAvailability']['opinionGroups'] is False
    assert data['dataAvailability']['personalLens'] is False
    assert data['opinionGroups'] == []
    assert statement['viewerGroupChoice'] is None
    assert statement['viewerMatchesGroup'] is None
    assert statement['personalDelta'] is None


def test_no_results_while_the_informed_round_is_open(
    client, auth_client, conversation, participant,
):
    """No live informed-round results (owner, 2026-10-13): informed voting alone opens
    nothing, for a joined participant as for a visitor."""
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='patient-owl',
    ))
    db.session.commit()

    with patch('app._build_phase6_results', return_value=_results()):
        anonymous = client.get('/api/v1/conversations/test-conv/results')
        joined = auth_client.get('/api/v1/conversations/test-conv/results')

    assert anonymous.status_code == 409
    assert joined.status_code == 409


def test_preliminary_results_projects_a_private_group_view_and_personal_delta(
    auth_client, conversation, participant,
):
    conversation.phase_public_results = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='reflective-fox',
    )
    db.session.add(participation)
    db.session.commit()
    results = _results()
    results['p6_participants'] = 30
    results['personal_lens_available'] = True
    results['statements'][0].update({
        'my_p2_vote': 1,
        'my_p6_vote': -1,
        'my_group_votes': {
            'n_agree': 8, 'n_disagree': 17, 'n_pass': 5, 'n_voters': 30,
        },
    })

    with patch('app._build_phase6_results', return_value=results):
        data = auth_client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    statement = data['statements'][0]
    assert data['dataAvailability']['personalLens'] is True
    assert statement['viewerChoice'] == 'agree'
    assert statement['viewerGroupChoice'] == 'disagree'
    assert statement['viewerMatchesGroup'] is False
    assert statement['personalDelta'] == {
        'initial': 'disagree', 'informed': 'agree', 'changed': True,
    }


def test_final_report_never_returns_the_private_personal_lens(
    auth_client, conversation, participant,
):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='reflective-fox',
    ))
    db.session.commit()
    results = _results()
    results['p6_participants'] = 30
    results['personal_lens_available'] = True
    results['statements'][0].update({
        'my_p2_vote': 1,
        'my_p6_vote': -1,
        'my_group_votes': {
            'n_agree': 8, 'n_disagree': 17, 'n_pass': 5, 'n_voters': 30,
        },
    })

    with patch('app._build_phase6_results', return_value=results):
        data = auth_client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    assert data['publication'] == 'final'
    assert data['dataAvailability']['personalLens'] is False
    statement = data['statements'][0]
    assert statement['viewerChoice'] is None
    assert statement['viewerGroupChoice'] is None
    assert statement['viewerMatchesGroup'] is None
    assert statement['personalDelta'] is None


def test_preliminary_personal_view_omits_tied_group_choice(
    auth_client, conversation, participant,
):
    conversation.phase_public_results = True
    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'private-phase6-id'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='reflective-fox',
    ))
    db.session.commit()
    results = _results()
    results['personal_lens_available'] = True
    results['statements'][0].update({
        'my_p2_vote': -1,
        'my_p6_vote': -1,
        'my_group_votes': {
            'n_agree': 10, 'n_disagree': 10, 'n_pass': 0, 'n_voters': 20,
        },
    })

    with patch('app._build_phase6_results', return_value=results):
        data = auth_client.get(
            '/api/v1/conversations/test-conv/results',
        ).get_json()['data']

    statement = data['statements'][0]
    assert statement['viewerGroupChoice'] is None
    assert statement['viewerMatchesGroup'] is None
    assert statement['personalDelta'] == {
        'initial': 'agree', 'informed': 'agree', 'changed': False,
    }


def test_phase6_results_withhold_personal_lens_until_privacy_gate_is_defined(
    conversation, participant,
):
    from app import _build_phase6_results

    conversation.phase6_polis_conversation_id = 'phase6abc123'
    statement = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        phase6_polis_statement_id=51,
        statement_text='A featured statement',
        confirmed_by_admin=True,
    )
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='reflective-fox',
    )
    db.session.add_all([statement, participation])
    db.session.commit()

    polis = MagicMock()
    polis.get_phase6_vote_counts.side_effect = [
        {51: {'n_agree': 3, 'n_disagree': 1, 'n_pass': 0, 'n_voters': 4}},
        {11: {'n_agree': 1, 'n_disagree': 2, 'n_pass': 0, 'n_voters': 3}},
    ]
    polis.get_phase6_participant_count.side_effect = [30, 20]
    with (
        patch('app._polis_server_client', return_value=polis),
        patch('app._phase6_agg_cached',
              side_effect=lambda _key, producer, cacheable=None: producer()),
        patch('app.PolisParticipantClient') as participant_client,
    ):
        participant_client.return_value.get_results.return_value = None
        result = _build_phase6_results(conversation, participation)

    assert result['personal_lens_available'] is False
    assert result['statements'][0]['my_group_votes'] is None
    polis.get_personal_votes.assert_not_called()


def test_preliminary_results_order_does_not_depend_on_cross_round_shift(
    app, conversation,
):
    from app import _build_phase6_results
    from services.results_report import build_results_report

    conversation.phase6_polis_conversation_id = 'phase6abc123'
    db.session.commit()
    specs = [(11, 51, 4), (12, 52, 1), (13, 53, 2), (14, 54, 3)]
    featured = [
        FeaturedStatement(
            conversation_id=conversation.id,
            polis_statement_id=p2_tid,
            phase6_polis_statement_id=p6_tid,
            statement_text=f'Statement {index}',
            confirmed_by_admin=True,
        )
        for index, (p2_tid, p6_tid, _) in enumerate(specs, start=1)
    ]
    db.session.add_all(featured)
    db.session.commit()

    p6_counts = {
        p6_tid: {'n_agree': 5, 'n_disagree': 5, 'n_pass': 0, 'n_voters': 10}
        for _, p6_tid, _ in specs
    }
    p2_counts = {
        p2_tid: {
            'n_agree': p2_agree,
            'n_disagree': 10 - p2_agree,
            'n_pass': 0,
            'n_voters': 10,
        }
        for p2_tid, _, p2_agree in specs
    }
    polis = MagicMock()
    polis.get_phase6_vote_counts.side_effect = lambda zinvite, *_args: (
        p6_counts if zinvite == conversation.phase6_polis_conversation_id else p2_counts
    )
    polis.get_phase6_participant_count.return_value = 10
    with (
        patch('app._polis_server_client', return_value=polis),
        patch('app._phase6_agg_cached',
              side_effect=lambda _key, producer, cacheable=None: producer()),
        patch('app.PolisParticipantClient') as participant_client,
    ):
        participant_client.return_value.get_results.return_value = None
        results = _build_phase6_results(
            conversation, None, Phase6ResultsFilter.empty(),
        )

    data = build_results_report(
        conversation=conversation,
        phase6_results=results,
        output_context={
            'phase': 'informed-voting', 'status': 'provisional',
            'method': 'deliberation',
        },
        participation=None,
        reveal_state=None,
        self_link='/results',
        conversation_link='/c/test-conv',
        about_link='/about',
        identity_reveal_link=None,
    )

    # Identical informed tallies must not let different P2→P6 shifts choose which
    # statements survive the public top-three tie cutoff.
    assert len({row['p6']['pct_agree'] for row in results['statements']}) == 1
    assert len({row['shift'] for row in results['statements']}) == 4
    assert [row['featuredStatementId'] for row in data['statements']] == [
        row.id for row in featured
    ]
    assert all(row['initial'] is None and row['agreementShift'] is None
               for row in data['statements'])
