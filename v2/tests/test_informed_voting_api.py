"""Informed-voting read and command API contract tests."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from db import (Argument, Conversation, ConversationBan, FeaturedStatement,
                Participation, db)
from services.informed_voting import build_informed_voting_state


def _response(payload=None, *, status=200, cookies=None):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.content = b'{}' if payload is not None else b''
    response.json.return_value = payload or {}
    response.cookies = cookies or {}
    return response


def _fixture(participant):
    conversation = Conversation(
        slug='informed-api', polis_id='phase2round', title='Informed API',
        active=True, access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='phase6round', phase_submission=True,
        phase_argument_mapping=True,
    )
    db.session.add(conversation)
    db.session.flush()
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='thoughtful-otter',
    )
    first = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=11,
        phase6_polis_statement_id=51, statement_text='First statement',
        confirmed_by_admin=True,
    )
    second = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=12,
        phase6_polis_statement_id=52, statement_text='Second statement',
        confirmed_by_admin=True,
    )
    db.session.add_all([participation, first, second])
    db.session.flush()
    participation.phase6_card_order = [first.id]
    db.session.add_all([
        Argument(featured_statement_id=first.id, side='pro', body='Useful context'),
        Argument(featured_statement_id=first.id, side='con', body='Important caveat'),
        Argument(
            featured_statement_id=first.id, side='pro', body='Hidden context',
            hidden=True,
        ),
    ])
    db.session.commit()
    return conversation, participation, first, second


def test_informed_voting_api_returns_private_progress_and_persists_new_cards(
    auth_client, participant,
):
    conversation, participation, first, second = _fixture(participant)
    session_response = _response(
        {'csrf_token': 'phase6-csrf'}, cookies={'session': 'phase6-cookie'},
    )
    participant_response = _response({'votes': [51], 'statements': []})

    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', return_value=participant_response),
    ):
        response = auth_client.get(
            '/api/v1/conversations/informed-api/informed-voting',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['progress'] == {
        'completed': 1, 'total': 2, 'remaining': 1, 'allDone': False,
    }
    assert [card['featuredStatementId'] for card in data['cards']] == [
        first.id, second.id,
    ]
    assert data['cards'][0]['voted'] is True
    assert data['cards'][0]['canVote'] is True
    assert data['cards'][1]['voted'] is False
    assert data['cards'][1]['canVote'] is True
    assert data['cards'][0]['arguments'] == {
        'for': [{'id': 1, 'body': 'Useful context', 'helpfulVotes': 0}],
        'against': [{'id': 2, 'body': 'Important caveat', 'helpfulVotes': 0}],
    }
    assert data['links']['explore'] == '/c/informed-api'
    assert data['links']['arguments'] == '/c/informed-api#tab-arguments'
    db.session.refresh(participation)
    assert participation.phase6_card_order == [first.id, second.id]
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert conversation.polis_id not in serialized
    assert conversation.phase6_polis_conversation_id not in serialized


def test_banned_participant_can_read_informed_round_but_cannot_vote(
    auth_client, participant,
):
    conversation, _participation, first, _second = _fixture(participant)
    db.session.add(ConversationBan(
        conversation_id=conversation.id,
        participant_id=participant.id,
        summary='Participation suspended',
    ))
    db.session.commit()
    session_response = _response(
        {'csrf_token': 'phase6-csrf'}, cookies={'session': 'phase6-cookie'},
    )

    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', return_value=_response({
            'votes': [], 'statements': [],
        })),
        patch('app.polis_http.put') as put,
    ):
        read = auth_client.get(
            '/api/v1/conversations/informed-api/informed-voting',
        )
        vote = auth_client.put(
            f'/api/v1/conversations/informed-api/featured-statements/{first.id}/informed-vote',
            json={'choice': 'agree'},
        )

    assert read.status_code == 200
    assert read.get_json()['data']['cards']
    assert vote.status_code == 403
    assert vote.get_json()['error']['code'] == 'forbidden'
    put.assert_not_called()


def test_informed_vote_is_idempotent_put_and_translates_phase6_sign(
    auth_client, participant,
):
    conversation, participation, first, _second = _fixture(participant)
    with auth_client.session_transaction() as browser_session:
        # Phase 6 sessions are keyed per conversation, exactly like Phase 2's
        # `particiapi_api_sessions` (see test_phase6_session_scope.py).
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): {
                'cookie': 'phase6-cookie', 'csrfToken': 'phase6-csrf',
            },
        }

    with patch('app.polis_http.put', return_value=_response({})) as put:
        response = auth_client.put(
            f'/api/v1/conversations/informed-api/featured-statements/{first.id}/informed-vote',
            json={'choice': 'agree'},
        )

    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'featuredStatementId': first.id,
        'choice': 'agree',
        'links': {
            'informedVoting': '/api/v1/conversations/informed-api/informed-voting',
        },
    }
    # Polis convention: -1 = agree, +1 = disagree, 0 = pass. Same as the Explore
    # path at app.py:2212, and what polis_admin.py:153 counts as agree_count.
    # This asserted {'value': 1} before, which locked in the inverted sign and is
    # why every informed vote on production was stored as its own opposite.
    # Verified against a live Polis: an agree in each phase now stores -1 in both.
    assert put.call_args.kwargs['json'] == {'value': -1}
    assert put.call_args.kwargs['cookies'] == {'session': 'phase6-cookie'}


@pytest.mark.parametrize('choice, polis_value', [
    ('agree', -1),
    ('pass', 0),
    ('disagree', 1),
])
def test_informed_vote_sends_polis_signs_for_every_choice(
    auth_client, participant, choice, polis_value,
):
    """Lock all three mappings, not just agree.

    With only `agree` asserted, mapping `disagree` to -1 as well would pass — the
    map would be wrong and no test would notice. These are the signs Polis stores
    and `polis_admin.py` counts, and they must match the Explore path exactly.
    """
    conversation, participation, first, _second = _fixture(participant)
    with auth_client.session_transaction() as browser_session:
        # Phase 6 sessions are keyed per conversation, exactly like Phase 2's
        # `particiapi_api_sessions` (see test_phase6_session_scope.py).
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): {
                'cookie': 'phase6-cookie', 'csrfToken': 'phase6-csrf',
            },
        }

    with patch('app.polis_http.put', return_value=_response({})) as put:
        response = auth_client.put(
            f'/api/v1/conversations/informed-api/featured-statements/{first.id}/informed-vote',
            json={'choice': choice},
        )

    assert response.status_code == 200
    assert put.call_args.kwargs['json'] == {'value': polis_value}
    db.session.refresh(participation)
    assert participation.last_engagement is not None


def test_informed_vote_rejects_featured_statement_from_another_round(
    auth_client, participant,
):
    _fixture(participant)

    with patch('app.polis_http.put') as put:
        response = auth_client.put(
            '/api/v1/conversations/informed-api/featured-statements/999/informed-vote',
            json={'choice': 'pass'},
        )

    assert response.status_code == 404
    put.assert_not_called()


def test_informed_voting_empty_round_is_not_reported_complete(participant):
    conversation = Conversation(
        slug='empty-informed', polis_id='empty-p2', title='Empty',
        active=True, access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='empty-p6',
    )
    db.session.add(conversation)
    db.session.flush()
    participation = Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='empty-otter',
    )
    db.session.add(participation)
    db.session.commit()

    data = build_informed_voting_state(
        conversation_id=conversation.id,
        participation=participation,
        participant_payload={'votes': []},
    )

    assert data['progress'] == {
        'completed': 0, 'total': 0, 'remaining': 0, 'allDone': False,
    }


def test_informed_voting_keeps_renderable_card_while_initialization_is_pending(
    participant,
):
    conversation = Conversation(
        slug='pending-informed', polis_id='pending-p2', title='Pending',
        active=True, access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='pending-p6',
    )
    db.session.add(conversation)
    db.session.flush()
    participation = Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='patient-otter',
    )
    statement = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=71,
        phase6_polis_statement_id=None, statement_text='Awaiting initialization',
        confirmed_by_admin=True,
    )
    db.session.add_all([participation, statement])
    db.session.commit()

    data = build_informed_voting_state(
        conversation_id=conversation.id,
        participation=participation,
        participant_payload={'votes': []},
    )

    assert data['cards'] == [{
        'featuredStatementId': statement.id,
        'statement': 'Awaiting initialization',
        'canVote': False,
        'voted': False,
        'arguments': {'for': [], 'against': []},
    }]
    assert data['progress'] == {
        'completed': 0, 'total': 1, 'remaining': 1, 'allDone': False,
    }


def test_openapi_documents_informed_voting_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    read = spec['paths']['/conversations/{slug}/informed-voting']['get']
    vote = spec['paths'][
        '/conversations/{slug}/featured-statements/{featuredStatementId}/informed-vote'
    ]['put']

    assert read['operationId'] == 'getInformedVoting'
    assert vote['operationId'] == 'putInformedVote'
    assert 'Idempotent' in vote['description']


def test_informed_vote_api_binds_the_same_identity_explore_uses(app, auth_client, participant):
    """The API write path must bind identity too, to the SAME subject Phase 2 uses.

    There are two Phase 6 write paths — this one and the legacy Jinja route — and they
    share `_p6_session_cache`. If only one bound, an anonymous session cached by the other
    would be handed straight to it and the binding would be silently defeated, so both
    need locking. See test_phase6_vote.py for the legacy half.
    """
    secret = 'shared-upstream-secret'
    app.config['PARTICIAPI_SUB_SECRET'] = secret
    conversation, _participation, first, _second = _fixture(participant)
    conv_id, xid = conversation.id, participant.xid

    # Deliberately do NOT pre-seed _p6_pa/_p6_csrf: the bootstrap must actually run.
    session_resp = _response({'csrf_token': 'tok'}, cookies={'session': 'pa-cookie'})
    with patch('app.polis_http.post', return_value=session_resp) as post, \
         patch('app.polis_http.put', return_value=_response({})):
        response = auth_client.put(
            f'/api/v1/conversations/informed-api/featured-statements/{first.id}/informed-vote',
            json={'choice': 'agree'},
        )

    assert response.status_code == 200
    headers = post.call_args.kwargs['headers']
    assert headers['X-Particiapi-Sub-Secret'] == secret
    expected = hmac.new(secret.encode(), f'{xid}:{conv_id}'.encode(), hashlib.sha256).hexdigest()
    assert headers['X-Particiapi-Sub'] == expected
    assert headers['X-Particiapi-Sub'] != xid
