"""Unit tests for polis_admin.py — all DB and HTTP calls are mocked."""
from unittest.mock import MagicMock, patch

import pytest
import requests as _requests

from polis_admin import (
    PolisParticipantClient, PolisParticipantError,
    PolisServerClient, PolisServerError,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_ok(json_data):
    resp = MagicMock()
    resp.ok = True
    resp.content = b'data'
    resp.json.return_value = json_data
    return resp


def _mock_err(status=500):
    resp = MagicMock()
    resp.ok = False
    resp.status_code = status
    resp.text = 'error'
    return resp


def _server_client():
    return PolisServerClient('http://polis:8001', 'admin@test.com', 'pass')


def _mock_login(client):
    """Patch _login to return a mock session + empty auth headers."""
    sess = MagicMock()
    return patch.object(type(client), '_login', return_value=(sess, {})), sess


# ── PolisParticipantClient.get_statements ─────────────────────────────────────

def test_get_statements_returns_all_as_approved():
    """Particiapi returns a dict; all statements normalised into approved."""
    client = PolisParticipantClient('http://localhost:8000')
    data = {'0': {'text': 'first stmt'}, '1': {'text': 'second stmt'}}
    with patch('polis_admin._http.request', return_value=_mock_ok(data)) as mock_req:
        pending, approved, hid = client.get_statements('abc123')

    assert pending == [] and hid == []
    assert len(approved) == 2
    assert {s['tid'] for s in approved} == {0, 1}
    assert any(s['txt'] == 'first stmt' for s in approved)
    assert mock_req.call_args[0][0] == 'GET'
    assert 'abc123/statements/' in mock_req.call_args[0][1]


def test_get_statements_non_dict_returns_empty():
    client = PolisParticipantClient('http://localhost:8000')
    with patch('polis_admin._http.request', return_value=_mock_ok([])):
        pending, approved, hid = client.get_statements('abc123')
    assert pending == approved == hid == []


def test_get_statements_http_error_raises():
    client = PolisParticipantClient('http://localhost:8000')
    with patch('polis_admin._http.request', return_value=_mock_err(503)):
        with pytest.raises(PolisParticipantError, match='503'):
            client.get_statements('abc123')


def test_get_statements_network_error_raises():
    client = PolisParticipantClient('http://localhost:8000')
    with patch('polis_admin._http.request',
               side_effect=_requests.RequestException('timeout')):
        with pytest.raises(PolisParticipantError, match='timeout'):
            client.get_statements('abc123')


def test_get_results_returns_none_on_error():
    client = PolisParticipantClient('http://localhost:8000')
    with patch('polis_admin._http.request', return_value=_mock_err(404)):
        assert client.get_results('abc123') is None


# ── PolisServerClient.get_polis_stats ─────────────────────────────────────────

def _make_stats_client(db_rows=None, db_error=None):
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    if db_error:
        cur.execute.side_effect = db_error
    else:
        cur.fetchall.return_value = [db_rows] if db_rows is not None else []
    return client, mock_conn


def test_stats_no_db_url_returns_none():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw', db_url='')
    assert client.get_polis_stats('abc123') is None


def test_stats_invalid_zinvite_returns_none():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    for bad in ('bad zinvite!', '', None, 'ab'):
        assert client.get_polis_stats(bad) is None


def test_stats_connection_error_returns_none():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    with patch('psycopg2.connect', side_effect=Exception('conn refused')):
        assert client.get_polis_stats('abc123') is None


def test_stats_retries_once_on_stale_connection(monkeypatch):
    # #275 M2: a pooled connection closed by the server during idle raises
    # OperationalError on first use; _pg_query retries once with a fresh borrow
    # instead of falsely reporting the stats unavailable.
    import psycopg2
    import polis_admin
    monkeypatch.setattr(polis_admin, '_get_pg_pool', lambda db_url: None)  # force fallback path
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    stale = MagicMock()
    stale.cursor.return_value.__enter__.return_value.execute.side_effect = \
        psycopg2.OperationalError('server closed the connection unexpectedly')
    fresh = MagicMock()
    fresh.cursor.return_value.__enter__.return_value.fetchall.return_value = \
        [(10, 150, 15.0, 12.5, 8, 3)]
    with patch('psycopg2.connect', side_effect=[stale, fresh]) as connect:
        result = client.get_polis_stats('abc123')
    assert result is not None and result['n_participants'] == 10
    assert connect.call_count == 2   # retried once on the stale connection


def test_pg_fallback_is_bounded_and_sheds_when_saturated(monkeypatch):
    # #275 M4: when the pool is exhausted AND the one-off fallback budget is
    # saturated, the read is shed (returns None / degraded) rather than opening an
    # unbounded connection that could exceed Postgres max_connections.
    import threading
    import polis_admin
    monkeypatch.setattr(polis_admin, '_get_pg_pool', lambda db_url: None)  # force fallback path
    saturated = threading.BoundedSemaphore(1)
    saturated.acquire()  # no fallback slots left
    monkeypatch.setattr(polis_admin, '_pg_fallback_sem', saturated)
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    with patch('psycopg2.connect') as connect:
        assert client.get_polis_stats('abc123') is None
        connect.assert_not_called()   # never opened an unbounded one-off connection


def test_stats_empty_row_returns_none():
    client, mock_conn = _make_stats_client(db_rows=None)
    with patch('psycopg2.connect', return_value=mock_conn):
        assert client.get_polis_stats('abc123') is None


def test_stats_returns_correct_dict():
    client, mock_conn = _make_stats_client(db_rows=(10, 150, 15.0, 12.5, 8, 3))
    with patch('psycopg2.connect', return_value=mock_conn):
        result = client.get_polis_stats('abc123')
    assert result == {
        'n_participants': 10, 'n_votes': 150, 'avg_votes': 15.0,
        'median_votes': 12.5, 'n_statements': 8, 'n_seed': 3,
    }
    # Pooled: a successful read returns the connection to the pool, not close().
    mock_conn.close.assert_not_called()


def test_valid_vote_count_returns_latest_vote_rows():
    client, mock_conn = _make_stats_client(db_rows=(7,))
    with patch('psycopg2.connect', return_value=mock_conn):
        assert client.get_valid_vote_count('abc123') == 7


def test_valid_vote_count_no_db_url_returns_none():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw', db_url='')
    assert client.get_valid_vote_count('abc123') is None


def test_stats_closes_connection_on_error():
    client, mock_conn = _make_stats_client(db_error=Exception('query boom'))
    with patch('psycopg2.connect', return_value=mock_conn):
        assert client.get_polis_stats('abc123') is None
    mock_conn.close.assert_called_once()


# ── PolisServerClient.queue_math_recompute ───────────────────────────────────

def test_queue_math_recompute_inserts_worker_task():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value

    with patch('psycopg2.connect', return_value=mock_conn):
        assert client.queue_math_recompute('abc123') is True

    sql = cur.execute.call_args.args[0]
    assert 'INSERT INTO worker_tasks' in sql
    assert cur.execute.call_args.args[1] == ('abc123',)
    mock_conn.commit.assert_called_once()
    # Pooled: a successful write returns the connection to the pool, not close().
    mock_conn.close.assert_not_called()


def test_queue_math_recompute_logs_worker_task_privilege_gap(caplog):
    import logging

    import psycopg2

    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    cur.execute.side_effect = psycopg2.errors.InsufficientPrivilege('permission denied')

    with caplog.at_level(logging.ERROR):
        with patch('psycopg2.connect', return_value=mock_conn):
            assert client.queue_math_recompute('abc123') is False

    assert 'grant INSERT on worker_tasks' in caplog.text
    mock_conn.close.assert_called_once()


# ── PolisServerClient.get_statement_progress_for_participants ────────────────

def test_statement_progress_for_participants_maps_by_xid():
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [('xidA', 5, 3, 2), ('xidB', 5, 0, 5)]
    with patch('psycopg2.connect', return_value=mock_conn):
        result = client.get_statement_progress_for_participants('abc123', ['xidA', 'xidB'])
    assert result == {
        'xidA': {'total': 5, 'voted': 3, 'remaining': 2},
        'xidB': {'total': 5, 'voted': 0, 'remaining': 5},
    }
    cur.execute.assert_called_once()  # one query for all participants, not per-participant


def test_statement_progress_for_participants_guards():
    no_db = PolisServerClient('http://polis', 'a@b.com', 'pw', db_url='')
    assert no_db.get_statement_progress_for_participants('abc123', ['x']) is None
    client = PolisServerClient('http://polis', 'a@b.com', 'pw',
                               db_url='postgresql://localhost/polis')
    assert client.get_statement_progress_for_participants('bad zinvite!', ['x']) is None
    assert client.get_statement_progress_for_participants('abc123', []) == {}


# ── PolisServerClient.create_conversation ────────────────────────────────────

def _setup_create(zinvite='abc123'):
    client = _server_client()
    sess = MagicMock()
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {'url': f'https://pol.is/{zinvite}', 'zid': 1}
    sess.post.return_value = resp
    login_patch = patch.object(PolisServerClient, '_login', return_value=(sess, {}))
    return client, sess, login_patch


def test_create_conversation_sends_strict_moderation_false_by_default():
    client, sess, login_patch = _setup_create()
    with login_patch:
        client.create_conversation('My conversation')
    payload = sess.post.call_args[1]['json']
    assert payload['strict_moderation'] is False


def test_create_conversation_strict_moderation_can_be_overridden():
    client, sess, login_patch = _setup_create()
    with login_patch:
        client.create_conversation('My conversation', strict_moderation=False)
    payload = sess.post.call_args[1]['json']
    assert payload['strict_moderation'] is False


def test_create_conversation_returns_zinvite():
    client, sess, login_patch = _setup_create(zinvite='xyz789')
    with login_patch:
        result = client.create_conversation('My conversation')
    assert result == 'xyz789'


def test_create_conversation_raises_on_polis_error():
    client, sess, login_patch = _setup_create()
    sess.post.return_value = _mock_err(500)
    with login_patch:
        with pytest.raises(PolisServerError):
            client.create_conversation('My conversation')


def test_close_and_hide_conversation_deactivates_and_hides_results():
    client = _server_client()
    login_patch, sess = _mock_login(client)
    sess.put.return_value = _mock_ok({})
    with login_patch:
        client.close_and_hide_conversation('abc123')

    payload = sess.put.call_args[1]['json']
    assert payload == {
        'conversation_id': 'abc123',
        'is_active': False,
        'vis_type': 0,
    }


def test_close_and_hide_conversation_raises_on_polis_error():
    client = _server_client()
    login_patch, sess = _mock_login(client)
    sess.put.return_value = _mock_err(500)
    with login_patch:
        with pytest.raises(PolisServerError):
            client.close_and_hide_conversation('abc123')
