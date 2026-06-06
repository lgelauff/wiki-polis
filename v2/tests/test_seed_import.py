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

    # Simulate bulk_add_seeds: run add_seed_side_effect once per text.
    def _bulk_add_seeds(conv_id, texts):
        successes = 0
        failures = []
        for text in texts:
            try:
                if add_seed_side_effect is not None:
                    if callable(add_seed_side_effect):
                        add_seed_side_effect(conv_id, text)
                    else:
                        raise add_seed_side_effect
                successes += 1
            except PolisServerError as exc:
                failures.append((text, exc))
        return successes, failures

    mock_client.bulk_add_seeds.side_effect = _bulk_add_seeds

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
    assert b'2 statements imported' in resp.data
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 2


def test_single_statement_grammar(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'text\nOnly one')
    assert b'1 statement imported' in resp.data


def test_header_only_no_data_rows(admin_client, conv):
    with _mock_polis():
        resp = _upload(admin_client, conv.id, b'text\n')
    assert b'No statements were imported' in resp.data


# ── Per-row error reporting ───────────────────────────────────────────────────

def test_empty_rows_reported_with_line_number(admin_client, conv):
    # Invalid row rejects the entire batch.
    csv = b'text\ngood\n\nalso good'
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'empty' in resp.data.lower()
    assert b'rejected' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_too_long_row_reported_with_line_number(admin_client, conv):
    # Invalid row rejects the entire batch.
    long_text = 'a' * 281
    csv = f'text\ngood\n{long_text}\nalso good'.encode('utf-8')
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'too long' in resp.data.lower()
    assert b'rejected' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_duplicate_within_file_reported_with_line_number(admin_client, conv):
    # Duplicate within the file rejects the entire batch.
    csv = b'text\nhello\nhello\nworld'
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    assert b'Row 3' in resp.data
    assert b'duplicate' in resp.data.lower()
    assert b'rejected' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_max_rows_limit_enforced(admin_client, conv):
    from seed_csv import MAX_ROWS
    rows = '\n'.join(f'Statement {i}' for i in range(MAX_ROWS + 3))
    csv = f'text\n{rows}'.encode('utf-8')
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == MAX_ROWS
    assert b'limit' in resp.data.lower()


# ── Deduplication against existing Polis statements ──────────────────────────

def test_skips_statements_already_in_polis(admin_client, conv):
    existing = [{'txt': 'Already there', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    csv = b'text\nAlready there\nNew one'
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        resp = _upload(admin_client, conv.id, csv)
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 1
    assert b'already exists' in resp.data.lower()
    assert b'1 imported' in resp.data


def test_dedup_is_case_insensitive(admin_client, conv):
    existing = [{'txt': 'Hello', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    csv = b'text\nhello\nHello\nHELLO'
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        _upload(admin_client, conv.id, csv)
    # All three are case-fold duplicates of 'Hello' — none should be sent
    assert mock.return_value.bulk_add_seeds.call_args is None or \
           mock.return_value.bulk_add_seeds.call_args[0][1] == []


def test_dedup_continues_when_polis_fetch_fails(admin_client, conv):
    """If get_statements raises, import proceeds without dedup and shows a warning."""
    csv = b'text\nStatement one\nStatement two'
    # side_effect list: first call (import route) raises; second call (redirect view) succeeds
    with _mock_polis() as mock:
        mock.return_value.get_statements.side_effect = [
            Exception('db down'),
            ([], [], []),
        ]
        resp = _upload(admin_client, conv.id, csv)
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 2
    assert b'Could not check for existing statements' in resp.data


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
    assert b'1 imported' in resp.data
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
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert texts_sent and not texts_sent[0].startswith('=')


def test_html_entity_formula_injection_stripped(admin_client, conv):
    # &equals; is the HTML entity for '=' — nh3 decodes it, so we must
    # re-strip formula prefixes after sanitisation.
    csv = 'text\n&equals;SUM(A1)'.encode('utf-8')
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    # &equals; decodes to '=' via nh3; second-pass strip_formula_prefixes must remove it.
    # The text becomes empty after stripping, so bulk_add_seeds must not be called at all.
    assert mock.return_value.bulk_add_seeds.call_args is None or \
           all(not t.startswith('=') for t in mock.return_value.bulk_add_seeds.call_args[0][1])


def test_all_tags_csv_produces_empty_string_and_is_not_sent(admin_client, conv):
    # A cell that is only HTML tags becomes '' after nh3.clean — must not be
    # sent to Polis as an empty seed statement.
    csv = b'text\n<b></b>'
    with _mock_polis() as mock:
        resp = _upload(admin_client, conv.id, csv)
    call_args = mock.return_value.bulk_add_seeds.call_args
    # Either not called at all, or called with no texts
    assert call_args is None or call_args[0][1] == []


def test_nh3_induced_duplicate_sent_only_once(admin_client, conv):
    # '<b>Hello</b>' and 'Hello' both sanitize to 'Hello' — only one
    # should reach Polis.
    csv = b'text\n<b>Hello</b>\nHello'
    with _mock_polis() as mock:
        _upload(admin_client, conv.id, csv)
    call_args = mock.return_value.bulk_add_seeds.call_args
    assert call_args is not None, "bulk_add_seeds should have been called"
    texts_sent = call_args[0][1]
    assert texts_sent.count('Hello') == 1
