"""Tests for participant-facing dashboard bucketing (#253)."""

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


def test_joined_paused_conversation_is_not_presented_as_active(
    auth_client, joined_conversation,
):
    joined_conversation.paused = True
    joined_conversation.phase_submission = True
    db.session.commit()

    page = auth_client.get('/consultations').data.decode()

    assert 'Inactive / paused' in page
    assert 'Test Conversation' in page
    assert 'Needs attention' not in page


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
        page = auth_client.get('/consultations').data.decode()

    assert 'Caught up' in page
    assert 'Test Conversation' in page


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
        page = auth_client.get('/consultations').data.decode()

    assert 'Needs attention' in page
    assert '3 to vote' in page
