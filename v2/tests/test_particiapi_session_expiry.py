"""Particiapi session expiry: re-bind before the cookie dies, and once on an empty read.

Production bug (2026-10-02): Particiapi signs its session cookie with a 7-day lifetime
(particiapi/config_defaults.py PERMANENT_SESSION_LIFETIME). wiki-polis cached that cookie
in its own 30-day session at bind time and never refreshed it. Once it expired,
GET /participant answered 200 with an EMPTY participant, so the Explore deck showed every
statement again, and answering a card again overwrote the earlier vote.

The fix re-binds when the cached state is missing, legacy (no ``boundAt``) or 6 days old,
and re-binds once when a cached session reads as an all-empty participant. The progress
queries now map subjects through ``particiapi_users`` instead of ``xids``.
"""

import hashlib
import hmac
import logging
import re
import time
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
import polis_admin
from db import Conversation, FeaturedStatement, Participation, db
from polis_admin import PolisServerClient
from services.explore import (SESSION_MAX_AGE_SECONDS, ExploreGateway,
                              ExploreUpstreamError, ParticiapiSessionState)
from tests.conftest import particiapi_state

SECRET = 'shared-upstream-secret'
SEVEN_DAYS = 7 * 24 * 60 * 60


def _response(payload=None, *, status=200, cookies=None):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.content = b'{}' if payload is not None else b''
    response.json.return_value = payload or {}
    response.cookies = cookies or {}
    return response


def _session(cookie='fresh-cookie', csrf='fresh-csrf'):
    return _response({'csrf_token': csrf}, cookies={'session': cookie})


def _subject(xid, conv_id):
    return hmac.new(SECRET.encode(), f'{xid}:{conv_id}'.encode(), hashlib.sha256).hexdigest()


STATEMENTS = {
    '10': {'id': 10, 'text': 'First statement'},
    '11': {'id': 11, 'text': 'Second statement'},
    '12': {'id': 12, 'text': 'Third statement'},
}
EMPTY = {'votes': [], 'statements': []}
ANSWERED = {'votes': [10, 11], 'statements': []}


@pytest.fixture
def bound_app(app):
    """Trusted-sub binding on, as in production."""
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    return app


def _join_explore(participant, conversation):
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='expiry-otter',
    ))
    conversation.phase_submission = True
    db.session.commit()


def _seed_explore(client, conversation, **kwargs):
    with client.session_transaction() as browser_session:
        browser_session['particiapi_api_sessions'] = {
            str(conversation.id): particiapi_state('old-cookie', 'old-csrf', **kwargs),
        }


# ── Phase 2 (Explore): the production bug ─────────────────────────────────────

def test_expired_session_reading_empty_is_rebound_and_shows_earlier_answers(
    bound_app, auth_client, participant, conversation,
):
    """The production case: a cookie that looks fresh to wiki-polis but that Particiapi
    no longer accepts reads as an empty participant. Fails on main: the empty read was
    trusted and the deck opened on statement 10 with 0 of 3 done."""
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation)

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),        # expired cookie
            _response(STATEMENTS), _response(ANSWERED),     # after the re-bind
        ]) as get,
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['currentStatement']['id'] == 12
    assert data['progress'] == {
        'completed': 2, 'total': 3, 'remaining': 1, 'allDone': False,
    }
    post.assert_called_once()
    assert post.call_args.kwargs['headers']['X-Particiapi-Sub'] == _subject(
        participant.xid, conversation.id,
    )
    assert get.call_args_list[2].kwargs['cookies'] == {'session': 'fresh-cookie'}
    with auth_client.session_transaction() as browser_session:
        stored = browser_session['particiapi_api_sessions'][str(conversation.id)]
    assert stored['cookie'] == 'fresh-cookie'


def test_genuinely_new_participant_pays_one_extra_bind_and_gets_the_deck(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation)

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
            _response(STATEMENTS), _response(EMPTY),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['progress']['completed'] == 0
    assert data['currentStatement'] is not None
    post.assert_called_once()  # exactly one re-bind, then the empty read is used


def test_session_bound_in_this_request_is_not_rebound_again_on_an_empty_read(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    post.assert_called_once()  # the first bind ('missing') only


def test_old_session_is_rebound_before_the_read(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, bound_at=time.time() - SEVEN_DAYS)

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(ANSWERED),
        ]) as get,
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    post.assert_called_once()
    assert get.call_args_list[0].kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_rebind_log_names_reason_phase_and_conversation_only(
    bound_app, auth_client, participant, conversation, caplog,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation)
    caplog.set_level(logging.INFO)

    with (
        patch('app.polis_http.post', return_value=_session()),
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
            _response(STATEMENTS), _response(ANSWERED),
        ]),
    ):
        auth_client.get('/api/v1/conversations/test-conv/explore')

    lines = [r.getMessage() for r in caplog.records if 're-bind' in r.getMessage()]
    assert lines == [
        f'Particiapi session re-bind: reason=empty-read '
        f'phase=explore conversation_id={conversation.id}',
    ]
    for secret_value in (
        participant.xid, _subject(participant.xid, conversation.id),
        participant.mw_username, 'old-cookie', 'fresh-cookie',
    ):
        assert secret_value not in caplog.text


# ── Gateway: when a cached session is re-bound ────────────────────────────────

NOW = 1_000_000.0


def _gateway(state, *, subject='scoped-subject'):
    transport = MagicMock()
    transport.post.return_value = _session()
    transport.get.return_value = _response(ANSWERED)
    gateway = ExploreGateway(
        base_url='https://particiapi.example',
        transport=transport,
        state=state,
        subject=subject,
        subject_secret='binding-secret' if subject else None,
        clock=lambda: NOW,
    )
    return gateway, transport


def _state(*, bound_at=NOW):
    return ParticiapiSessionState('cached-cookie', 'cached-csrf', bound_at=bound_at)


def test_fresh_state_is_used_without_a_session_post():
    gateway, transport = _gateway(_state(bound_at=NOW - 3600))
    gateway.read_participant('zinvite1')
    transport.post.assert_not_called()
    assert transport.get.call_args.kwargs['cookies'] == {'session': 'cached-cookie'}


def test_legacy_state_without_bound_at_is_rebound():
    legacy = ParticiapiSessionState.from_dict({'cookie': 'c', 'csrfToken': 't'})
    gateway, transport = _gateway(legacy)
    assert gateway.rebind_reason() == 'legacy'
    gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    assert gateway.state.bound_at == NOW


def test_state_older_than_max_age_is_rebound():
    gateway, transport = _gateway(_state(bound_at=NOW - SESSION_MAX_AGE_SECONDS))
    assert gateway.rebind_reason() == 'age'
    gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    # Bound sessions start clean: the old cookie is not sent with the bind.
    assert transport.post.call_args.kwargs['cookies'] == {}
    assert transport.get.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_max_age_is_below_particiapis_seven_days():
    assert SESSION_MAX_AGE_SECONDS < SEVEN_DAYS


def test_bind_without_a_fresh_cookie_is_refused_when_binding():
    """A bound session must come from this bind: never date-stamp an old cookie."""
    gateway, transport = _gateway(_state(bound_at=0.0))
    transport.post.return_value = _response({'csrf_token': 'tok'})  # no Set-Cookie
    with pytest.raises(ExploreUpstreamError):
        gateway.ensure_session()
    assert gateway.state.bound_at == 0.0


def test_unbound_age_refresh_keeps_the_anonymous_cookie():
    """Without trusted-sub, sending the old cookie keeps the same anonymous uid."""
    gateway, transport = _gateway(
        ParticiapiSessionState('anon-cookie', 'anon-csrf', bound_at=0.0), subject=None,
    )
    transport.post.return_value = _response({'csrf_token': 'tok'})  # no Set-Cookie
    gateway.ensure_session()
    assert transport.post.call_args.kwargs['cookies'] == {'session': 'anon-cookie'}
    assert transport.post.call_args.kwargs['params'] == {'create': 'true'}
    assert gateway.state.cookie == 'anon-cookie'


def test_empty_read_rebinds_once_then_uses_what_comes_back():
    gateway, transport = _gateway(_state())
    transport.get.return_value = _response(EMPTY)
    assert gateway.read_participant('zinvite1') == EMPTY
    transport.post.assert_called_once()
    assert transport.get.call_count == 2


def test_unbound_empty_read_is_not_rebound():
    """Without trusted-sub a re-bind would mint a new anonymous uid, not recover one."""
    gateway, transport = _gateway(_state(), subject=None)
    transport.get.return_value = _response(EMPTY)
    assert gateway.read_participant('zinvite1') == EMPTY
    transport.post.assert_not_called()


def test_rejected_session_then_empty_read_binds_only_once():
    gateway, transport = _gateway(_state())
    transport.get.side_effect = [_response(status=403), _response(EMPTY)]
    assert gateway.read_participant('zinvite1') == EMPTY
    transport.post.assert_called_once()


def test_session_state_round_trips_and_degrades_to_rebind():
    state = _state()
    assert ParticiapiSessionState.from_dict(state.to_dict()) == state
    assert ParticiapiSessionState.from_dict({'boundAt': 'yesterday'}).bound_at is None
    assert ParticiapiSessionState.from_dict({'boundAt': True}).bound_at is None
    assert ParticiapiSessionState.from_dict(('cookie', 'csrf')).cookie is None


# ── Phase 6 (informed voting) ─────────────────────────────────────────────────

def _phase6_fixture(participant):
    conversation = Conversation(
        slug='expiry-p6', polis_id='expiryp2round', title='Expiry P6',
        active=True, access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='expiryp6round',
    )
    db.session.add(conversation)
    db.session.flush()
    participation = Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='p6-otter',
    )
    first = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=11,
        phase6_polis_statement_id=51, statement_text='First featured',
        confirmed_by_admin=True,
    )
    second = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=12,
        phase6_polis_statement_id=52, statement_text='Second featured',
        confirmed_by_admin=True,
    )
    db.session.add_all([participation, first, second])
    db.session.commit()
    return conversation, first


def _informed_vote(client, first):
    return client.put(
        f'/api/v1/conversations/expiry-p6/featured-statements/{first.id}/informed-vote',
        json={'choice': 'pass'},
    )


def test_phase6_expired_session_reading_empty_is_rebound_and_shows_answered_cards(
    bound_app, auth_client, participant,
):
    conversation, first = _phase6_fixture(participant)
    with auth_client.session_transaction() as browser_session:
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): particiapi_state('old-p6-cookie', 'old-p6-csrf'),
        }

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(EMPTY), _response({'votes': [51], 'statements': []}),
        ]) as get,
    ):
        response = auth_client.get('/api/v1/conversations/expiry-p6/informed-voting')

    assert response.status_code == 200
    cards = response.get_json()['data']['cards']
    assert {card['featuredStatementId']: card['voted'] for card in cards} == {
        first.id: True, first.id + 1: False,
    }
    post.assert_called_once()
    assert get.call_args_list[1].kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_phase6_legacy_state_is_rebound_before_voting(bound_app, auth_client, participant):
    conversation, first = _phase6_fixture(participant)
    with auth_client.session_transaction() as browser_session:
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): {'cookie': 'legacy', 'csrfToken': 'legacy-csrf'},
        }

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = _informed_vote(auth_client, first)

    assert vote.status_code == 200
    post.assert_called_once()
    assert put.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}


@pytest.mark.parametrize('cached', [
    particiapi_state('cached-old', 'cached-old-csrf', bound_at=time.time() - SEVEN_DAYS),
    {'cookie': 'cached-legacy', 'csrfToken': 'cached-legacy-csrf'},
    ('cached-tuple', 'cached-tuple-csrf'),  # the shape cached before this change
], ids=['old', 'legacy', 'tuple'])
def test_phase6_process_cache_does_not_hand_out_an_old_or_legacy_session(
    bound_app, auth_client, participant, cached,
):
    conversation, first = _phase6_fixture(participant)
    app_module._p6_session_cache[(participant.xid, conversation.id)] = cached

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = _informed_vote(auth_client, first)

    assert vote.status_code == 200
    post.assert_called_once()
    assert put.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}
    assert app_module._p6_session_cache[(participant.xid, conversation.id)]['cookie'] == (
        'fresh-cookie'
    )


def test_phase6_process_cache_shares_a_fresh_session(bound_app, auth_client, participant):
    conversation, first = _phase6_fixture(participant)
    app_module._p6_session_cache[(participant.xid, conversation.id)] = particiapi_state(
        'shared-cookie', 'shared-csrf',
    )

    with (
        patch('app.polis_http.post') as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = _informed_vote(auth_client, first)

    assert vote.status_code == 200
    post.assert_not_called()
    assert put.call_args.kwargs['cookies'] == {'session': 'shared-cookie'}


# ── Polis Postgres queries: subject → particiapi_users, never xids ────────────

def _sql_constants():
    return {
        name: value for name, value in vars(polis_admin).items()
        if name.endswith('_SQL') and isinstance(value, str)
    }


def test_no_polis_admin_query_references_xids():
    """``xids.zid`` needs Polis migration 000015, absent on production, and nothing writes
    ``xids`` under trusted-sub: every such query failed with ``column x.zid does not
    exist``."""
    constants = _sql_constants()
    assert len(constants) >= 8  # the scan is actually looking at the queries
    offenders = [
        name for name, sql in constants.items()
        if re.search(r'\bxids?\b', sql, flags=re.IGNORECASE)
    ]
    assert offenders == []


def _pg_client():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    return client, mock_conn, cur


def test_progress_bulk_sends_per_conversation_subjects_and_the_issuer():
    client, mock_conn, cur = _pg_client()
    cur.fetchall.return_value = [('abc123', 4, 3, 1)]
    with patch('psycopg2.connect', return_value=mock_conn):
        result = client.get_statement_progress_bulk({
            'abc123': 'subject-a', 'bad zinvite!': 'subject-x', 'def456': 'subject-d',
            'ghi789': None,
        })
    assert result == {'abc123': {'total': 4, 'voted': 3, 'remaining': 1}}
    sql, params = cur.execute.call_args.args
    assert sql is polis_admin._STATEMENTS_REMAINING_BULK_SQL
    assert params == (['abc123', 'def456'], ['subject-a', 'subject-d'], 'wiki-polis')


def test_progress_for_participants_sends_subjects_and_the_issuer():
    client, mock_conn, cur = _pg_client()
    cur.fetchall.return_value = [('s1', 4, 2, 2)]
    with patch('psycopg2.connect', return_value=mock_conn):
        progress = client.get_statement_progress_for_participants('abc123', ['s1', None])
    assert progress == {'s1': {'total': 4, 'voted': 2, 'remaining': 2}}
    sql, params = cur.execute.call_args.args
    assert sql is polis_admin._STATEMENT_PROGRESS_BY_SUBJECT_SQL
    assert params == ('abc123', ['s1'], 'wiki-polis')


def test_home_lane_asks_for_progress_by_conversation_scoped_subject(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)

    with patch('app.PolisServerClient.get_statements_remaining_bulk',
               return_value={conversation.polis_id: 1}) as bulk:
        response = auth_client.get('/api/v1/conversations')

    assert response.status_code == 200
    bulk.assert_called_once_with({
        conversation.polis_id: _subject(participant.xid, conversation.id),
    })


def test_about_page_asks_for_progress_by_conversation_scoped_subject(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)

    with patch('app.PolisServerClient.get_statement_progress_bulk',
               return_value={conversation.polis_id: {'voted': 2}}) as bulk:
        response = auth_client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 200
    assert response.get_json()['data']['personal']['statementVotes'] == 2
    bulk.assert_called_once_with({
        conversation.polis_id: _subject(participant.xid, conversation.id),
    })


def _progress_queries(pg):
    return [
        call for call in pg.call_args_list
        if call.args[0] in (polis_admin._STATEMENTS_REMAINING_BULK_SQL,
                            polis_admin._STATEMENT_PROGRESS_BY_SUBJECT_SQL)
    ]


def test_without_a_sub_secret_participant_progress_reports_no_count(
    app, auth_client, participant, conversation,
):
    """No trusted-sub binding means no subject to look up: report no count, never
    "every statement remaining", and do not query Polis Postgres for it."""
    app.config['PARTICIAPI_SUB_SECRET'] = ''
    app.config['POLIS_DATABASE_URL'] = 'postgresql://polis.invalid/polis'
    _join_explore(participant, conversation)

    with patch('polis_admin.PolisServerClient._pg_query', return_value=None) as pg:
        lanes = auth_client.get('/api/v1/conversations').get_json()['data']['groups']
        about = auth_client.get('/api/v1/conversations/test-conv/about').get_json()['data']

    entries = [entry for group in lanes.values() for entry in group
               if entry['slug'] == 'test-conv']
    assert entries and all(entry['statementsRemaining'] is None for entry in entries)
    assert about['personal']['statementVotes'] is None
    assert _progress_queries(pg) == []


def test_without_a_sub_secret_admin_roster_reports_no_count(
    app, admin_client, participant, conversation,
):
    app.config['PARTICIAPI_SUB_SECRET'] = ''
    app.config['POLIS_DATABASE_URL'] = 'postgresql://polis.invalid/polis'
    _join_explore(participant, conversation)

    with patch('polis_admin.PolisServerClient._pg_query', return_value=None) as pg:
        roster = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/participants',
        ).get_json()['data']

    rows = [row for row in roster['participants'] if row['pseudonym'] == 'expiry-otter']
    assert rows and rows[0]['statementProgress'] is None
    assert _progress_queries(pg) == []
