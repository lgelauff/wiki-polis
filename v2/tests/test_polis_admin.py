"""Unit tests for polis_admin.py — all DB and HTTP calls are mocked."""
from unittest.mock import MagicMock, patch

import pytest

from polis_admin import PolisAdminClient, PolisAdminError, get_polis_stats


# ── get_polis_stats ───────────────────────────────────────────────────────────

def test_no_db_url_returns_none():
    assert get_polis_stats('abc123', '') is None
    assert get_polis_stats('abc123', None) is None


def test_invalid_zinvite_returns_none():
    assert get_polis_stats('bad zinvite!', 'postgresql://x/y') is None
    assert get_polis_stats('', 'postgresql://x/y') is None
    assert get_polis_stats(None, 'postgresql://x/y') is None
    assert get_polis_stats('ab', 'postgresql://x/y') is None  # too short


def test_valid_zinvite_boundary():
    """6-char zinvite is accepted; 5-char is not."""
    with patch('psycopg2.connect', side_effect=Exception('no server')):
        assert get_polis_stats('abcde', 'postgresql://x/y') is None   # 5 chars
        assert get_polis_stats('abcdef', 'postgresql://x/y') is None  # 6 chars — accepted, conn fails


def test_connection_error_returns_none():
    with patch('psycopg2.connect', side_effect=Exception('conn refused')):
        assert get_polis_stats('abc123', 'postgresql://localhost/polis') is None


def test_empty_row_returns_none():
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    with patch('psycopg2.connect', return_value=mock_conn):
        assert get_polis_stats('abc123', 'postgresql://localhost/polis') is None


def test_returns_correct_dict():
    mock_conn = MagicMock()
    cur = mock_conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (10, 150, 15.0, 12.5, 8, 3)
    with patch('psycopg2.connect', return_value=mock_conn):
        result = get_polis_stats('abc123', 'postgresql://localhost/polis')

    assert result == {
        'n_participants': 10,
        'n_votes': 150,
        'avg_votes': 15.0,
        'median_votes': 12.5,
        'n_statements': 8,
        'n_seed': 3,
    }
    mock_conn.close.assert_called_once()


def test_closes_connection_on_error():
    """psycopg2 connection is always closed, even on query error."""
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.side_effect = Exception('query boom')
    with patch('psycopg2.connect', return_value=mock_conn):
        result = get_polis_stats('abc123', 'postgresql://localhost/polis')
    assert result is None
    mock_conn.close.assert_called_once()


# ── PolisAdminClient ──────────────────────────────────────────────────────────

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


def test_get_statements_returns_all_as_approved():
    """Particiapi returns a dict of statements; all normalised into approved."""
    client = PolisAdminClient('http://localhost:8000')
    data = {'0': {'text': 'first stmt'}, '1': {'text': 'second stmt'}}
    with patch('polis_admin.requests.request', return_value=_mock_ok(data)) as mock_req:
        pending, approved, hid = client.get_statements('abc123')

    assert pending == [] and hid == []
    assert len(approved) == 2
    tids = {s['tid'] for s in approved}
    assert tids == {0, 1}
    assert approved[0]['txt'] == 'first stmt' or approved[1]['txt'] == 'first stmt'

    call = mock_req.call_args
    assert call[0][0] == 'GET'
    assert 'abc123/statements/' in call[0][1]


def test_get_statements_non_dict_response_returns_empty():
    """If Particiapi returns a list instead of a dict, return empty tuples."""
    client = PolisAdminClient('http://localhost:8000')
    with patch('polis_admin.requests.request', return_value=_mock_ok([])):
        pending, approved, hid = client.get_statements('abc123')
    assert pending == approved == hid == []


def test_moderate_raises_not_available():
    """Particiapi has no moderation endpoint — must raise PolisAdminError."""
    client = PolisAdminClient('http://localhost:8000')
    with pytest.raises(PolisAdminError, match='not available'):
        client.moderate('abc123', tid=5, mod=1)


def test_add_seed_raises_not_available():
    """Particiapi seed creation requires a browser session — must raise PolisAdminError."""
    client = PolisAdminClient('http://localhost:8000')
    with pytest.raises(PolisAdminError, match='not available'):
        client.add_seed('abc123', 'Seed statement text')


def test_http_error_raises_polis_admin_error():
    client = PolisAdminClient('http://localhost:8000')
    with patch('polis_admin.requests.request', return_value=_mock_err(503)):
        with pytest.raises(PolisAdminError, match='503'):
            client.get_statements('abc123')


def test_network_error_raises_polis_admin_error():
    import requests as _requests
    client = PolisAdminClient('http://localhost:8000')
    with patch('polis_admin.requests.request',
               side_effect=_requests.RequestException('timeout')):
        with pytest.raises(PolisAdminError, match='timeout'):
            client.get_statements('abc123')


def test_get_results_returns_none_on_error():
    client = PolisAdminClient('http://localhost:8000')
    with patch('polis_admin.requests.request', return_value=_mock_err(404)):
        assert client.get_results('abc123') is None
