"""Tests for participant-facing dashboard bucketing (#253)."""

from datetime import datetime

import pytest

from db import Participation, db
from services.conversation_lanes import classify_joined_conversation


@pytest.fixture
def joined_conversation(conversation, participant):
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='lane-fox',
    ))
    db.session.commit()
    return conversation


@pytest.mark.parametrize(
    ('values', 'expected'),
    [
        ({'active': False, 'paused': False, 'phases': {'closed'},
          'statements_remaining': None}, 'archived'),
        ({'active': True, 'paused': True, 'phases': {'submission'},
          'statements_remaining': 4}, 'inactive'),
        ({'active': True, 'paused': False, 'phases': {'preparation'},
          'statements_remaining': None}, 'inactive'),
        ({'active': True, 'paused': False, 'phases': {'submission'},
          'statements_remaining': 0}, 'caught_up'),
        ({'active': True, 'paused': False, 'phases': {'submission'},
          'statements_remaining': 2}, 'needs_attention'),
        ({'active': True, 'paused': False, 'phases': {'argument_mapping'},
          'statements_remaining': 0}, 'needs_attention'),
    ],
)
def test_classify_joined_conversation(values, expected):
    assert classify_joined_conversation(**values) == expected


def _lanes(client):
    resp = client.get('/api/v1/conversations')
    assert resp.status_code == 200
    return resp.get_json()['data']['groups']


def _slugs(groups, lane):
    return [c['slug'] for c in groups[lane]]


def _entry(groups, lane, slug):
    return next(c for c in groups[lane] if c['slug'] == slug)


def test_joined_paused_conversation_is_not_presented_as_active(
    auth_client, joined_conversation,
):
    joined_conversation.paused = True
    joined_conversation.phase_submission = True
    db.session.commit()

    groups = _lanes(auth_client)

    assert _slugs(groups, 'inactive') == ['test-conv']
    assert _entry(groups, 'inactive', 'test-conv')['title'] == 'Test Conversation'
    assert _slugs(groups, 'needsAttention') == []


def test_joined_participant_with_no_explore_votes_left_is_caught_up(
    auth_client, joined_conversation,
):
    joined_conversation.phase_submission = True
    db.session.commit()

    from unittest.mock import patch

    with patch(
        'app.PolisServerClient.get_statements_remaining_bulk',
        return_value={joined_conversation.polis_id: 0},
    ):
        groups = _lanes(auth_client)

    assert _slugs(groups, 'caughtUp') == ['test-conv']
    entry = _entry(groups, 'caughtUp', 'test-conv')
    assert entry['title'] == 'Test Conversation'
    assert entry['participantState'] == 'caught_up'


def test_joined_participant_with_explore_work_needs_attention(
    auth_client, joined_conversation,
):
    joined_conversation.phase_submission = True
    db.session.commit()

    from unittest.mock import patch

    with patch(
        'app.PolisServerClient.get_statements_remaining_bulk',
        return_value={joined_conversation.polis_id: 3},
    ):
        groups = _lanes(auth_client)

    assert _slugs(groups, 'needsAttention') == ['test-conv']
    entry = _entry(groups, 'needsAttention', 'test-conv')
    assert entry['participantState'] == 'needs_attention'
    assert entry['statementsRemaining'] == 3          # the "3 to vote" the page showed


def test_dashboard_shows_scheduled_transition_target_and_semantic_time(
    auth_client, joined_conversation,
):
    joined_conversation.phase_submission = True
    joined_conversation.scheduled_transition_at = datetime(2026, 8, 20, 14, 30)
    joined_conversation.scheduled_transition_target = 'argument_mapping'
    db.session.commit()

    groups = _lanes(auth_client)

    # The page rendered "Next: Arguments" inside a <time datetime=...> the client
    # localised. The label and the machine-readable UTC instant are the server's
    # half of that; the <time> element and data-local-datetime hook are the SPA's.
    scheduled = _entry(groups, 'needsAttention', 'test-conv')['scheduledTransition']
    assert scheduled['target'] == 'argument_mapping'
    assert scheduled['targetLabel'] == 'Arguments'
    assert scheduled['at'] == '2026-08-20T14:30:00Z'
