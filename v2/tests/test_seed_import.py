"""Flask integration tests for POST /admin/conversations/<id>/statements/seed/import."""
import io
from unittest.mock import MagicMock, patch

import pytest

from db import Conversation, db
from polis_admin import PolisServerError
from tests.conftest import login


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def conv(app):
    c = Conversation(
        slug='import-test', polis_id='zzz9999999',
        title='Import Test Conv', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


def _upload(client, conv_id, content: bytes, filename='statements.csv',
            content_type='text/csv'):
    return client.post(
        f'/admin/conversations/{conv_id}/statements/seed/import',
        data={'csv_file': (io.BytesIO(content), filename, content_type)},
        content_type='multipart/form-data',
        follow_redirects=True,
    )


def _mock_polis(add_seed_side_effect=None, existing_statements=None):
    """Return a context manager that patches _polis_server_client."""
    mock_client = MagicMock()
    if add_seed_side_effect:
        mock_client.add_seed.side_effect = add_seed_side_effect
    if existing_statements is not None:
        mock_client.get_statements.return_value = existing_statements
    else:
        mock_client.get_statements.return_value = ([], [], [])
    return patch('app._polis_server_client', return_value=mock_client)


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_unauthenticated_redirects_to_login(client, conv):
    resp = client.post(
        f'/admin/conversations/{conv.id}/statements/seed/import',
        data={'csv_file': (io.BytesIO(b'text\nhello'), 'f.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code in (302, 301)
    assert 'login' in resp.headers['Location'].lower()


def test_non_admin_forbidden(auth_client, conv):
    resp = _upload(auth_client, conv.id, b'text\nhello')
    assert resp.status_code == 403


# ── File validation ───────────────────────────────────────────────────────────

def test_no_file_selected(admin_client, conv):
    with _mock_polis():
        resp = admin_client.post(
            f'/admin/conversations/{conv.id}/statements/seed/import',
            data={},
            content_type='multipart/form-data',
            follow_redirects=True,
        )
    assert b'No file selected' in resp.data


def test_wrong_extension_rejected(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'text\nhello', filename='data.txt')
    assert b'.csv' in resp.data


def test_file_over_limit_rejected(admin_client, conv):
    big = b'text\n' + b'a' * (100 * 1024 + 1)
    with _mock_polis():
        resp = _upload(admin_client, conv.id, big)
    assert b'too large' in resp.data.lower()


def test_non_utf8_file_rejected(admin_client, conv):
    raw = 'text\nCaf\xe9'.encode('latin-1')
    with _mock_polis():
        resp = _upload(admin_client, conv.id, raw)
    assert b'UTF-8' in resp.data


def test_missing_text_column_rejected(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'note\nsome note')
    assert b'text' in resp.data.lower()


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_csv_imports_statements(admin_client, conv):
    csv = b'text\nStatement one\nStatement two'
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert b'2 seed statement' in resp.data
    assert mock.return_value.add_seed.call_count == 2


def test_single_statement_grammar(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'text\nOnly one')
    assert b'1 seed statement imported' in resp.data


def test_header_only_no_data_rows(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'text\n')
    assert b'No statements were imported' in resp.data


# ── Per-row error reporting ───────────────────────────────────────────────────

def test_empty_rows_reported_with_line_number(admin_client, conv):
    csv = b'text\ngood\n\nalso good'
    with _mock_polis():
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'empty' in resp.data.lower()
    assert b'2 seed statement' in resp.data


def test_too_long_row_reported_with_line_number(admin_client, conv):
    long_text = 'a' * 281
    csv = f'text\ngood\n{long_text}\nalso good'.encode('utf-8')
    with _mock_polis():
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'too long' in resp.data.lower()
    assert b'2 seed statement' in resp.data


def test_duplicate_within_file_reported_with_line_number(admin_client, conv):
    csv = b'text\nhello\nhello\nworld'
    with _mock_polis():
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'duplicate' in resp.data.lower()
    assert b'2 seed statement' in resp.data


def test_max_rows_limit_enforced(admin_client, conv):
    from seed_csv import MAX_ROWS
    rows = '\n'.join(f'Statement {i}' for i in range(MAX_ROWS + 3))
    csv = f'text\n{rows}'.encode('utf-8')
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert mock.return_value.add_seed.call_count == MAX_ROWS
    assert b'limit' in resp.data.lower()


# ── Deduplication against existing Polis statements ──────────────────────────

def test_skips_statements_already_in_polis(admin_client, conv):
    existing = [{'txt': 'Already there', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    csv = b'text\nAlready there\nNew one'
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert mock.return_value.add_seed.call_count == 1
    assert b'already exists' in resp.data.lower()
    assert b'1 seed statement imported' in resp.data


def test_dedup_is_case_sensitive(admin_client, conv):
    existing = [{'txt': 'Hello', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    csv = b'text\nhello\nHello\nHELLO'
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        resp = _upload(admin_client, conv.id, csv)
    # 'hello' and 'HELLO' are new; 'Hello' is a duplicate
    assert mock.return_value.add_seed.call_count == 2


def test_dedup_continues_when_polis_fetch_fails(admin_client, conv):
    """If get_statements raises, import proceeds without dedup rather than failing."""
    csv = b'text\nStatement one\nStatement two'
    # side_effect list: first call (import route) raises; second call (redirect view) succeeds
    with _mock_polis() as mock:
        mock.return_value.get_statements.side_effect = [
            Exception('db down'),
            ([], [], []),
        ]
        resp = _upload(admin_client, conv.id, csv)
    assert mock.return_value.add_seed.call_count == 2


# ── Polis API failures ────────────────────────────────────────────────────────

def test_polis_api_failure_reported(admin_client, conv):
    csv = b'text\nStatement one\nStatement two'
    with _mock_polis(add_seed_side_effect=PolisServerError('timeout')):
        resp = _upload(admin_client, conv.id, csv)
    assert b'Failed to send to Polis' in resp.data


def test_partial_polis_failure_still_imports_others(admin_client, conv):
    results = [None, PolisServerError('nope')]

    def side_effect(*a, **kw):
        r = results.pop(0)
        if r is not None:
            raise r

    csv = b'text\nGood one\nBad one'
    with _mock_polis(add_seed_side_effect=side_effect):
        resp = _upload(admin_client, conv.id, csv)
    assert b'1 seed statement imported' in resp.data
    assert b'Failed to send to Polis' in resp.data


# ── Security ─────────────────────────────────────────────────────────────────

def test_xss_in_statement_text_is_escaped(admin_client, conv):
    csv = b'text\n<script>alert(1)</script>'
    with _mock_polis():
        resp = _upload(admin_client, conv.id, csv)
    assert b'<script>' not in resp.data


def test_formula_injection_stripped_before_add_seed(admin_client, conv):
    csv = b'text\n=DANGEROUS'
    with _mock_polis() as mock:
        _upload(admin_client, conv.id, csv)
    call_args = mock.return_value.add_seed.call_args
    assert call_args is not None
    submitted_text = call_args[0][1]
    assert not submitted_text.startswith('=')
