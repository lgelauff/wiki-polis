"""The results API enforces the reporting rules on the server (#233).

Who gets which view (owner, 2026-10-31): participants, the process's organizers and site
admins get the full report (exact counts, groups); everyone else gets the public one
(percentages only, no groups). Below 10 responses no view carries a number.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import app as app_module
from app import Phase6ResultsFilter
from db import AdminRole, FeaturedStatement, Participation, db
from tests.conftest import login


def _row(fs_id, p2, p6, shift=None):
    def counts(agree, pass_, disagree):
        return {'n_agree': agree, 'n_pass': pass_, 'n_disagree': disagree,
                'n_voters': agree + pass_ + disagree}
    return {
        'fs_id': fs_id, 'text': f'Statement {fs_id}',
        'p2': counts(*p2) if p2 else None, 'p6': counts(*p6),
        'shift': shift, 'my_p6_vote': None,
    }


def _results():
    return {
        'statements': [
            _row(1, (6, 2, 4), (8, 1, 3), shift=17),   # 12 and 12 responses
            # 9 and 8: below the floor. The row's own shift is set on purpose: the report
            # must not pass it through for a withheld tally.
            _row(2, (3, 2, 4), (5, 1, 2), shift=40),
        ],
        'p2_participants': 30, 'p6_participants': 28, 'matched_participants': None,
        'filter': Phase6ResultsFilter.empty(),
        'clusters': [{'agree': [{'statement_text': 'Shared', 'value': .8}], 'disagree': []}],
        'pg_available': True,
    }


@pytest.fixture
def closed(conversation):
    conversation.active = False
    conversation.phase_public_results = True
    conversation.closed_at = datetime.now(timezone.utc)
    conversation.phase6_polis_conversation_id = 'phase6-id'
    db.session.commit()
    return conversation


def _report(client):
    with patch('app._build_phase6_results', return_value=_results()):
        response = client.get('/api/v1/conversations/test-conv/results')
    assert response.status_code == 200
    return response.get_json()['data']


def _is_full(data):
    shown = data['statements'][0]['informed']
    return shown['counts'] is not None and data['opinionGroups'] != []


def _is_public(data):
    shown = data['statements'][0]['informed']
    return shown['counts'] is None and shown['percentages'] is not None and data['opinionGroups'] == []


def test_logged_out_reader_gets_the_public_view(client, closed):
    data = _report(client)
    assert _is_public(data)
    assert data['statements'][0]['informed']['percentages'] == {
        'agree': 67, 'pass': 8, 'disagree': 25,
    }


def test_participant_gets_the_full_view(auth_client, closed, participant):
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=closed.id, pseudonym='quiet-otter',
    ))
    db.session.commit()
    data = _report(auth_client)
    assert _is_full(data)
    assert data['statements'][0]['informed']['counts'] == {
        'agree': 8, 'pass': 1, 'disagree': 3, 'voters': 12,
    }


def test_logged_in_non_participant_gets_the_public_view(auth_client, closed):
    assert _is_public(_report(auth_client))


def test_site_admin_gets_the_full_view_without_joining(admin_client, closed):
    data = _report(admin_client)
    assert _is_full(data)
    assert data['viewer']['participating'] is False


def test_organizer_gets_the_full_view_and_a_moderator_the_public_one(
    client, closed, participant,
):
    role = AdminRole(participant_id=participant.id, conversation_id=closed.id, role='moderator')
    db.session.add(role)
    db.session.commit()
    login(client, 'testuser')
    assert _is_public(_report(client))

    role.role = 'organizer'
    db.session.commit()
    assert _is_full(_report(client))


@pytest.mark.parametrize('viewer', ['public', 'site admin'])
def test_tally_below_the_floor_carries_no_number_in_any_view(
    viewer, client, admin_participant, closed,
):
    if viewer == 'site admin':
        login(client, 'adminuser')
    withheld = _report(client)['statements'][1]
    assert withheld['initial'] == {'counts': None, 'percentages': None, 'belowFloor': True}
    assert withheld['informed'] == {'counts': None, 'percentages': None, 'belowFloor': True}
    assert withheld['agreementShift'] is None


class _StubPolisServer:
    def __init__(self, p2, p6):
        self.counts = {'phase2-zinvite': p2, 'phase6-zinvite': p6}

    def get_phase6_vote_counts(self, zinvite, allowed_tids, excluded_pids=None):
        return {t: self.counts[zinvite][t] for t in allowed_tids if t in self.counts[zinvite]}

    def get_phase6_participant_count(self, zinvite, excluded_pids=None):
        return 20


def _counts(agree, pass_, disagree):
    return {'n_agree': agree, 'n_pass': pass_, 'n_disagree': disagree,
            'n_voters': agree + pass_ + disagree}


def test_builder_shift_needs_the_floor_in_both_rounds_and_rounds_once(app, conversation):
    conversation.polis_id = 'phase2-zinvite'
    conversation.phase6_polis_conversation_id = 'phase6-zinvite'
    db.session.add_all([
        FeaturedStatement(conversation_id=conversation.id, polis_statement_id=tid,
                          phase6_polis_statement_id=tid + 100, confirmed_by_admin=True,
                          statement_text=f'Statement {tid}')
        for tid in (1, 2, 3)
    ])
    db.session.commit()
    stub = _StubPolisServer(
        p2={1: _counts(2, 0, 14),    # 12.5% agree of 16
            2: _counts(2, 0, 7),     # 9 responses: below the floor
            3: _counts(5, 0, 5)},
        p6={101: _counts(10, 0, 20),  # 33.3% agree of 30
            102: _counts(5, 0, 5),
            103: _counts(4, 0, 5)},   # 9 responses: below the floor
    )
    with app.test_request_context(), \
            patch.object(app_module, '_polis_server_client', return_value=stub), \
            patch.object(app_module, 'PolisParticipantClient') as pa:
        pa.return_value.get_results.return_value = None
        results = app_module._build_phase6_results(conversation, None)

    shifts = {row['text']: row['shift'] for row in results['statements']}
    # 33.33 - 12.5 = 20.83 -> 21; the rounded shares (33 - 13) would give 20.
    assert shifts == {'Statement 1': 21, 'Statement 2': None, 'Statement 3': None}


def _join(client):
    return client.post('/api/v1/conversations/test-conv/participation',
                       json={'consent': True, 'pseudonym': 'late-otter'})


def test_nobody_new_can_join_a_closed_process_to_get_the_full_view(auth_client, closed, participant):
    # The full view follows a participation, so joining after close must not be a way in.
    refused = _join(auth_client)

    assert refused.status_code == 409
    assert refused.get_json()['error']['code'] == 'join_closed'
    assert Participation.query.filter_by(participant_id=participant.id).count() == 0
    assert _is_public(_report(auth_client))


def test_an_existing_participation_still_replays_after_close(auth_client, closed, participant):
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=closed.id, pseudonym='late-otter',
    ))
    db.session.commit()

    assert _join(auth_client).status_code == 200


def test_joining_an_open_process_still_works(auth_client, conversation):
    assert _join(auth_client).status_code == 201
