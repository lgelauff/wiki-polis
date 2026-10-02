"""Particiapi session expiry: re-bind before the cookie dies, and never trust an empty read.

Production bug (2026-10-02): Particiapi signs its session cookie with a 7-day lifetime
(particiapi/config_defaults.py PERMANENT_SESSION_LIFETIME). wiki-polis cached that cookie
in its own 30-day session at bind time and never refreshed it. Once it expired:

* GET /participant answered 200 with an EMPTY participant (particiapi/api.py, the
  ``not have_session()`` branch), so the Explore deck showed every statement again;
* the next vote PUT got 403, wiki-polis re-bound to the right uid and recorded the vote,
  overwriting the participant's earlier answer on that statement.

The fix re-binds on age/subject/legacy state, and checks every participant read against
Polis Postgres (the answer guard). These tests mock the Particiapi transport and the
Postgres count; the SQL itself is exercised offline against a real Polis schema (PR notes).
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
from services.explore import (DEFAULT_SESSION_MAX_AGE_SECONDS, ExploreGateway,
                              ParticiapiSessionState, ParticipantAnswersUnavailable,
                              subject_digest)
from tests.conftest import particiapi_state

SECRET = 'shared-upstream-secret'
SEVEN_DAYS = 7 * 24 * 60 * 60
PG_COUNT = 'app.PolisServerClient.get_participant_vote_count'


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
    """Trusted-sub binding on and Polis Postgres configured, as in production."""
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    app.config['POLIS_DATABASE_URL'] = 'postgresql://polis.invalid/polis'
    return app


def _join_explore(participant, conversation):
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='expiry-otter',
    ))
    conversation.phase_submission = True
    db.session.commit()


def _seed_explore(client, conversation, participant, **kwargs):
    with client.session_transaction() as browser_session:
        browser_session['particiapi_api_sessions'] = {
            str(conversation.id): particiapi_state(
                'old-cookie', 'old-csrf',
                subject=_subject(participant.xid, conversation.id), **kwargs,
            ),
        }


# ── Phase 2 (Explore): the production bug ─────────────────────────────────────

def test_expired_session_reading_empty_is_rebound_and_shows_earlier_answers(
    bound_app, auth_client, participant, conversation,
):
    """The production case: a cookie that looks fresh to wiki-polis but that Particiapi
    no longer accepts reads as an empty participant while Polis holds two answers.

    Fails on main: the empty read was trusted and the deck opened on statement 10 with
    0 of 3 done.
    """
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=2) as pg_count,
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),        # expired cookie
            _response(STATEMENTS), _response(ANSWERED),     # after the re-bind
        ]),
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
    pg_count.assert_called_once_with(conversation.polis_id, _subject(
        participant.xid, conversation.id,
    ))
    with auth_client.session_transaction() as browser_session:
        stored = browser_session['particiapi_api_sessions'][str(conversation.id)]
    assert stored['cookie'] == 'fresh-cookie'


def test_persistent_mismatch_returns_error_state_instead_of_a_deck(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=2),
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
            _response(STATEMENTS), _response(EMPTY),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 502
    error = response.get_json()['error']
    assert error['code'] == 'answers_unavailable'
    assert 'data' not in response.get_json()
    post.assert_called_once()  # exactly one forced re-bind, then give up


def test_persistent_mismatch_refuses_the_vote_without_sending_it(
    bound_app, auth_client, participant, conversation,
):
    """The overwrite half of the bug: the vote must never reach Particiapi."""
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=2),
        patch('app.polis_http.post', return_value=_session()),
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
            _response(STATEMENTS), _response(EMPTY),
        ]),
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        response = auth_client.put(
            '/api/v1/conversations/test-conv/statements/10/vote',
            json={'choice': 'agree'},
        )

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'answers_unavailable'
    put.assert_not_called()


def test_vote_goes_through_when_particiapi_and_polis_agree(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=2),
        patch('app.polis_http.post') as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(ANSWERED),
        ]),
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        response = auth_client.put(
            '/api/v1/conversations/test-conv/statements/12/vote',
            json={'choice': 'agree'},
        )

    assert response.status_code == 200
    post.assert_not_called()
    put.assert_called_once()


def test_postgres_unavailable_skips_the_guard(
    bound_app, auth_client, participant, conversation,
):
    """No count to compare with: the read is used as it is, without an extra re-bind."""
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=None),
        patch('app.polis_http.post') as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    assert response.get_json()['data']['progress']['completed'] == 0
    post.assert_not_called()


def test_postgres_unavailable_still_rebinds_an_old_session(
    bound_app, auth_client, participant, conversation,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant, bound_at=time.time() - SEVEN_DAYS)

    with (
        patch(PG_COUNT, return_value=None),
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(ANSWERED),
        ]) as get,
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    post.assert_called_once()
    # The re-bind happened BEFORE the read, so the read used the new cookie.
    assert get.call_args_list[0].kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_postgres_not_configured_never_queries_it(
    app, auth_client, participant, conversation,
):
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    app.config['POLIS_DATABASE_URL'] = ''
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)

    with (
        patch(PG_COUNT) as pg_count,
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    pg_count.assert_not_called()


def test_rebind_and_mismatch_logs_carry_no_identity(
    bound_app, auth_client, participant, conversation, caplog,
):
    _join_explore(participant, conversation)
    _seed_explore(auth_client, conversation, participant)
    caplog.set_level(logging.INFO)

    with (
        patch(PG_COUNT, return_value=2),
        patch('app.polis_http.post', return_value=_session()),
        patch('app.polis_http.get', side_effect=[
            _response(STATEMENTS), _response(EMPTY),
            _response(STATEMENTS), _response(ANSWERED),
        ]),
    ):
        auth_client.get('/api/v1/conversations/test-conv/explore')

    text = caplog.text
    assert 'reason=mismatch' in text
    assert 'particiapi_votes=0 polis_votes=2' in text
    assert f'conversation_id={conversation.id}' in text
    assert 'phase=explore' in text
    for secret_value in (
        participant.xid, _subject(participant.xid, conversation.id),
        participant.mw_username, 'old-cookie', 'fresh-cookie',
    ):
        assert secret_value not in text


# ── Gateway: when a cached session is re-bound ────────────────────────────────

def _gateway(state, *, subject='scoped-subject', now=1_000_000.0, expected=None):
    transport = MagicMock()
    transport.post.return_value = _session()
    transport.get.return_value = _response({'votes': [], 'statements': []})
    gateway = ExploreGateway(
        base_url='https://particiapi.example',
        transport=transport,
        state=state,
        subject=subject,
        subject_secret='binding-secret',
        expected_vote_count=expected,
        clock=lambda: now,
    )
    return gateway, transport


def _state(*, bound_at=1_000_000.0, subject='scoped-subject'):
    return ParticiapiSessionState(
        'cached-cookie', 'cached-csrf', bound_at=bound_at,
        subject_digest=subject_digest(subject),
    )


def test_fresh_state_is_used_without_a_session_post():
    gateway, transport = _gateway(_state(bound_at=1_000_000.0 - 3600))
    gateway.read_participant('zinvite1')
    transport.post.assert_not_called()
    assert transport.get.call_args.kwargs['cookies'] == {'session': 'cached-cookie'}


def test_legacy_state_without_bound_at_is_rebound():
    legacy = ParticiapiSessionState.from_dict({'cookie': 'c', 'csrfToken': 't'})
    gateway, transport = _gateway(legacy)
    assert gateway.rebind_reason() == 'legacy'
    gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    assert gateway.state.bound_at == 1_000_000.0
    assert gateway.state.subject_digest == subject_digest('scoped-subject')


def test_state_older_than_max_age_is_rebound():
    gateway, transport = _gateway(_state(
        bound_at=1_000_000.0 - DEFAULT_SESSION_MAX_AGE_SECONDS,
    ))
    assert gateway.rebind_reason() == 'age'
    gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    # Bound sessions start clean: the old cookie is not sent with the bind.
    assert transport.post.call_args.kwargs['cookies'] == {}
    assert transport.get.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_default_max_age_is_below_particiapis_seven_days():
    assert DEFAULT_SESSION_MAX_AGE_SECONDS < SEVEN_DAYS


def test_bound_at_in_the_future_is_treated_as_stale():
    gateway, _ = _gateway(_state(bound_at=1_000_000.0 + 86_400))
    assert gateway.rebind_reason() == 'age'


def test_subject_change_is_rebound():
    gateway, transport = _gateway(_state(subject='someone-else'))
    assert gateway.rebind_reason() == 'subject'
    gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    assert transport.post.call_args.kwargs['headers']['X-Particiapi-Sub'] == 'scoped-subject'


def test_bind_without_a_fresh_cookie_is_refused_when_binding():
    """A bound session must come from this bind: never date-stamp an old cookie."""
    gateway, transport = _gateway(_state(bound_at=0.0))
    transport.post.return_value = _response({'csrf_token': 'tok'})  # no Set-Cookie
    with pytest.raises(app_module.ExploreUpstreamError):
        gateway.ensure_session()


def test_unbound_age_refresh_keeps_the_anonymous_cookie():
    """Without trusted-sub, sending the old cookie keeps the same anonymous uid."""
    state = ParticiapiSessionState('anon-cookie', 'anon-csrf', bound_at=0.0)
    gateway, transport = _gateway(state, subject=None)
    gateway.ensure_session()
    assert transport.post.call_args.kwargs['cookies'] == {'session': 'anon-cookie'}
    assert transport.post.call_args.kwargs['params'] == {'create': 'true'}


def test_session_state_round_trips_and_never_holds_the_subject():
    state = _state()
    stored = state.to_dict()
    assert 'scoped-subject' not in repr(stored)
    assert ParticiapiSessionState.from_dict(stored) == state
    # Malformed stored values degrade to "re-bind", not to a crash.
    assert ParticiapiSessionState.from_dict({'boundAt': 'yesterday'}).bound_at is None
    assert ParticiapiSessionState.from_dict({'boundAt': True}).bound_at is None
    assert ParticiapiSessionState.from_dict({'boundAt': float('nan')}).bound_at is None
    assert ParticiapiSessionState.from_dict({'boundAt': float('inf')}).bound_at is None
    assert ParticiapiSessionState.from_dict('not-a-dict').cookie is None


def test_guard_reads_postgres_before_particiapi():
    """A vote landing between the two reads then makes Particiapi larger, not smaller."""
    order = []
    gateway, transport = _gateway(_state(), expected=lambda zinvite: order.append('pg') or 0)
    transport.get.side_effect = lambda *a, **k: order.append('particiapi') or _response(EMPTY)
    gateway.read_participant('zinvite1')
    assert order == ['pg', 'particiapi']


def test_guard_raises_after_one_forced_rebind():
    gateway, transport = _gateway(_state(), expected=lambda zinvite: 3)
    with pytest.raises(ParticipantAnswersUnavailable):
        gateway.read_participant('zinvite1')
    transport.post.assert_called_once()
    assert transport.get.call_count == 2


def test_guard_probe_exception_is_treated_as_unavailable():
    def broken(zinvite):
        raise RuntimeError('pool exhausted')

    gateway, transport = _gateway(_state(), expected=broken)
    assert gateway.read_participant('zinvite1') == EMPTY
    transport.post.assert_not_called()


def test_verify_answers_is_a_noop_without_the_guard():
    gateway, transport = _gateway(_state())
    gateway.verify_answers('zinvite1')
    transport.get.assert_not_called()


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


def _seed_phase6(client, conversation, participant, **kwargs):
    with client.session_transaction() as browser_session:
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): particiapi_state(
                'old-p6-cookie', 'old-p6-csrf',
                subject=_subject(participant.xid, conversation.id), **kwargs,
            ),
        }


def test_phase6_expired_session_is_rebound_and_shows_answered_cards(
    bound_app, auth_client, participant,
):
    conversation, first = _phase6_fixture(participant)
    _seed_phase6(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=1) as pg_count,
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.get', side_effect=[
            _response(EMPTY), _response({'votes': [51], 'statements': []}),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/expiry-p6/informed-voting')

    assert response.status_code == 200
    cards = response.get_json()['data']['cards']
    assert {card['featuredStatementId']: card['voted'] for card in cards} == {
        first.id: True, first.id + 1: False,
    }
    post.assert_called_once()
    # Phase 6 is checked against ITS Polis conversation, with the shared subject.
    pg_count.assert_called_once_with(
        'expiryp6round', _subject(participant.xid, conversation.id),
    )


def test_phase6_persistent_mismatch_refuses_the_informed_vote(
    bound_app, auth_client, participant,
):
    conversation, first = _phase6_fixture(participant)
    _seed_phase6(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=1),
        patch('app.polis_http.post', return_value=_session()),
        patch('app.polis_http.get', side_effect=[_response(EMPTY), _response(EMPTY)]),
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = auth_client.put(
            f'/api/v1/conversations/expiry-p6/featured-statements/{first.id}/informed-vote',
            json={'choice': 'agree'},
        )

    assert vote.status_code == 502
    assert vote.get_json()['error']['code'] == 'answers_unavailable'
    put.assert_not_called()


def test_phase6_persistent_mismatch_returns_error_state_on_read(
    bound_app, auth_client, participant,
):
    conversation, _first = _phase6_fixture(participant)
    _seed_phase6(auth_client, conversation, participant)

    with (
        patch(PG_COUNT, return_value=1),
        patch('app.polis_http.post', return_value=_session()),
        patch('app.polis_http.get', side_effect=[_response(EMPTY), _response(EMPTY)]),
    ):
        response = auth_client.get('/api/v1/conversations/expiry-p6/informed-voting')

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'answers_unavailable'


def test_phase6_legacy_state_is_rebound_before_voting(app, auth_client, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conversation, first = _phase6_fixture(participant)
    with auth_client.session_transaction() as browser_session:
        browser_session['phase6_api_sessions'] = {
            str(conversation.id): {'cookie': 'legacy', 'csrfToken': 'legacy-csrf'},
        }

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = auth_client.put(
            f'/api/v1/conversations/expiry-p6/featured-statements/{first.id}/informed-vote',
            json={'choice': 'pass'},
        )

    assert vote.status_code == 200
    post.assert_called_once()
    assert put.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}


def test_phase6_process_cache_does_not_hand_out_an_old_session(
    app, auth_client, participant,
):
    """The per-worker share cache must age out exactly like the browser-session copy."""
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conversation, first = _phase6_fixture(participant)
    subject = _subject(participant.xid, conversation.id)
    app_module._p6_session_cache[(participant.xid, conversation.id)] = particiapi_state(
        'cached-old', 'cached-old-csrf', subject=subject, bound_at=time.time() - SEVEN_DAYS,
    )

    with (
        patch('app.polis_http.post', return_value=_session()) as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = auth_client.put(
            f'/api/v1/conversations/expiry-p6/featured-statements/{first.id}/informed-vote',
            json={'choice': 'pass'},
        )

    assert vote.status_code == 200
    post.assert_called_once()
    assert put.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}
    cached = app_module._p6_session_cache[(participant.xid, conversation.id)]
    assert cached['cookie'] == 'fresh-cookie'


def test_phase6_process_cache_shares_a_fresh_session(app, auth_client, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conversation, first = _phase6_fixture(participant)
    subject = _subject(participant.xid, conversation.id)
    app_module._p6_session_cache[(participant.xid, conversation.id)] = particiapi_state(
        'shared-cookie', 'shared-csrf', subject=subject,
    )

    with (
        patch('app.polis_http.post') as post,
        patch('app.polis_http.put', return_value=_response({})) as put,
    ):
        vote = auth_client.put(
            f'/api/v1/conversations/expiry-p6/featured-statements/{first.id}/informed-vote',
            json={'choice': 'pass'},
        )

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
    ``xids`` under trusted-sub. Every query there failed with ``column x.zid does not
    exist``."""
    constants = _sql_constants()
    assert len(constants) >= 8  # the scan is actually looking at the queries
    offenders = [
        name for name, sql in constants.items()
        if re.search(r'\bxids?\b', sql, flags=re.IGNORECASE)
    ]
    assert offenders == []


def _pg_client(**kwargs):
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis', **kwargs)
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    return client, mock_conn, cur


def test_progress_bulk_sends_per_conversation_subjects_and_the_issuer():
    client, mock_conn, cur = _pg_client()
    cur.fetchall.return_value = [('abc123', 4, 3, 1)]
    with patch('psycopg2.connect', return_value=mock_conn):
        result = client.get_statement_progress_bulk({
            'abc123': 'subject-a', 'bad zinvite!': 'subject-x', 'def456': 'subject-d',
        })
    assert result == {'abc123': {'total': 4, 'voted': 3, 'remaining': 1}}
    sql, params = cur.execute.call_args.args
    assert sql is polis_admin._STATEMENTS_REMAINING_BULK_SQL
    assert params == (['abc123', 'def456'], ['subject-a', 'subject-d'], 'wiki-polis')


def test_progress_for_participants_and_vote_count_use_the_configured_issuer():
    client, mock_conn, cur = _pg_client(particiapi_issuer='other-issuer')
    cur.fetchall.side_effect = [[('s1', 4, 2, 2)], [(7,)]]
    with patch('psycopg2.connect', return_value=mock_conn):
        progress = client.get_statement_progress_for_participants('abc123', ['s1'])
        count = client.get_participant_vote_count('abc123', 's1')
    assert progress == {'s1': {'total': 4, 'voted': 2, 'remaining': 2}}
    assert count == 7
    first, second = cur.execute.call_args_list
    assert first.args[1] == ('abc123', ['s1'], 'other-issuer')
    assert second.args[0] is polis_admin._PARTICIPANT_VOTE_COUNT_SQL
    assert second.args[1] == ('s1', 'other-issuer', 'abc123')


def test_vote_count_guards_return_none_not_zero():
    """None means "cannot tell" (guard skipped); 0 would mean "nothing answered"."""
    no_db = PolisServerClient('http://polis', 'a@b.com', 'pw', db_url='')
    assert no_db.get_participant_vote_count('abc123', 's1') is None
    client, _, _ = _pg_client()
    assert client.get_participant_vote_count('bad zinvite!', 's1') is None
    assert client.get_participant_vote_count('abc123', '') is None


def test_issuer_is_configurable(app):
    app.config['PARTICIAPI_SUB_ISSUER'] = 'staging-issuer'
    with app.app_context():
        assert app_module._polis_server_client()._issuer == 'staging-issuer'
    app.config['PARTICIAPI_SUB_ISSUER'] = ''
    with app.app_context():
        assert app_module._polis_server_client()._issuer == 'wiki-polis'


def test_home_lane_asks_for_progress_by_conversation_scoped_subject(
    app, auth_client, participant, conversation,
):
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    _join_explore(participant, conversation)

    with patch('app.PolisServerClient.get_statements_remaining_bulk',
               return_value={conversation.polis_id: 1}) as bulk:
        response = auth_client.get('/api/v1/conversations')

    assert response.status_code == 200
    bulk.assert_called_once_with({
        conversation.polis_id: _subject(participant.xid, conversation.id),
    })


def test_about_page_asks_for_progress_by_conversation_scoped_subject(
    app, auth_client, participant, conversation,
):
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    _join_explore(participant, conversation)

    with patch('app.PolisServerClient.get_statement_progress_bulk',
               return_value={conversation.polis_id: {'voted': 2}}) as bulk:
        response = auth_client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 200
    assert response.get_json()['data']['personal']['statementVotes'] == 2
    bulk.assert_called_once_with({
        conversation.polis_id: _subject(participant.xid, conversation.id),
    })


def test_max_age_above_particiapis_lifetime_is_refused_at_startup(monkeypatch):
    from app import create_app
    monkeypatch.setenv('PARTICIAPI_SESSION_MAX_AGE_SECONDS', str(SEVEN_DAYS))
    with pytest.raises(RuntimeError, match='PARTICIAPI_SESSION_MAX_AGE_SECONDS'):
        create_app()


def test_guard_warns_when_polis_has_no_record_for_an_answering_participant(caplog):
    gateway, transport = _gateway(_state(), expected=lambda zinvite: 0)
    transport.get.return_value = _response(ANSWERED)
    caplog.set_level(logging.WARNING)
    assert gateway.read_participant('zinvite1') == ANSWERED
    assert 'check PARTICIAPI_SUB_ISSUER' in caplog.text
