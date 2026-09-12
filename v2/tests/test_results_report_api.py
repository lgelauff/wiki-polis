"""Privacy-safe preliminary/final results API contract tests."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from app import Phase6ResultsFilter
from db import Participation, db


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
    assert data['statements'][0]['viewerChoice'] == 'agree'


def test_openapi_documents_results_report_and_pass_counts(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/conversations/{slug}/results']['get']
    counts = spec['components']['schemas']['VoteTally']['properties']['counts']

    assert operation['operationId'] == 'getResultsReport'
    assert 'pass' in counts['required']
    assert 'pass' in counts['properties']


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
