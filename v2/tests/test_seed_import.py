"""Flask integration tests for POST /admin/conversations/<id>/statements/seed/import-text.

The bulk seed import is text-area only (the redundant CSV upload was removed per the
#236 review). These cover the shared post-parse pipeline — dedup-vs-Polis, Polis-failure
handling, row/byte limits, sanitisation — through the text endpoint.
"""
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


def _text_import(client, conv_id, text: str):
    return client.post(
        f'/admin/conversations/{conv_id}/statements/seed/import-text',
        data={'statement_texts': text},
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
        f'/admin/conversations/{conv.id}/statements/seed/import-text',
        data={'statement_texts': 'hello'},
    )
    assert resp.status_code in (302, 301)
    assert 'login' in resp.headers['Location'].lower()


def test_non_admin_forbidden(auth_client, conv):
    resp = auth_client.post(
        f'/admin/conversations/{conv.id}/statements/seed/import-text',
        data={'statement_texts': 'hello'},
    )
    assert resp.status_code == 403


# ── Happy path ────────────────────────────────────────────────────────────────

def test_text_imports_statements(admin_client, conv):
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'Statement one\nStatement two')
    assert b'2 statements imported' in resp.data
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 2


def test_single_statement_grammar(admin_client, conv):
    with _mock_polis():
        resp = _text_import(admin_client, conv.id, 'Only one')
    assert b'1 statement imported' in resp.data


def test_text_imports_one_statement_per_non_empty_line(admin_client, conv):
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'One\n\nTwo\n  Three  ')
    assert b'3 statements imported' in resp.data
    assert mock.return_value.bulk_add_seeds.call_args[0][1] == ['One', 'Two', 'Three']


def test_seed_import_allowed_in_preparation(admin_client, conv):
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'Prep seed')
    assert resp.status_code == 200
    mock.return_value.bulk_add_seeds.assert_called_once()


def test_seed_import_allowed_during_submission(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'Submission seed')
    assert resp.status_code == 200
    mock.return_value.bulk_add_seeds.assert_called_once()


def test_seed_import_locked_after_submission_phase(admin_client, conv):
    conv.phase_personal_results = True
    db.session.commit()
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'Too late')
    assert b'statement submission has ended' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_args is None


def test_seed_import_locked_in_argument_phase(admin_client, conv):
    conv.phase_argument_mapping = True
    db.session.commit()
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'Too late')
    assert b'statement submission has ended' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_args is None


def test_single_seed_locked_when_conversation_closed(admin_client, conv):
    conv.active = False
    db.session.commit()
    with _mock_polis() as mock:
        resp = admin_client.post(
            f'/admin/conversations/{conv.id}/statements/seed',
            data={'txt': 'Closed seed'},
            follow_redirects=True,
        )
    assert b'permanently closed' in resp.data.lower()
    mock.return_value.add_seed.assert_not_called()


def test_statements_page_hides_seed_forms_when_locked(admin_client, conv):
    conv.phase_cleanup = True
    db.session.commit()
    with _mock_polis():
        resp = admin_client.get(f'/admin/conversations/{conv.id}/statements')
    assert b'Seed statements locked' in resp.data
    assert b'Add seed statement</button>' not in resp.data
    assert b'name="statement_texts"' not in resp.data


def test_text_import_empty_input_imports_nothing(admin_client, conv):
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, '   \n  \n')
    assert b'No statements were imported' in resp.data
    assert mock.return_value.bulk_add_seeds.call_args is None


# ── Row / byte limits and per-row error reporting ─────────────────────────────

def test_text_import_rejects_overlong_line(admin_client, conv):
    long_text = 'x' * 281
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, f'Good\n{long_text}')
    assert b'Row 2' in resp.data
    assert b'too long' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_text_import_duplicate_within_paste_rejects_batch(admin_client, conv):
    # A duplicate line within the paste rejects the whole batch (all-or-nothing).
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, 'hello\nhello\nworld')
    assert b'Row 2' in resp.data
    assert b'duplicate' in resp.data.lower()
    assert b'rejected' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_text_import_enforces_row_limit(admin_client, conv):
    from seed_csv import MAX_ROWS
    rows = '\n'.join(f'Statement {i}' for i in range(MAX_ROWS + 1))
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, rows)
    assert b'rejected' in resp.data.lower()
    assert b'maximum is' in resp.data.lower()
    assert str(MAX_ROWS + 1).encode() in resp.data
    assert mock.return_value.bulk_add_seeds.call_args is None


def test_text_import_exactly_max_rows_accepted(admin_client, conv):
    """Exactly MAX_ROWS valid lines should import without rejection."""
    from seed_csv import MAX_ROWS
    rows = '\n'.join(f'Statement {i}' for i in range(MAX_ROWS))
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, rows)
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == MAX_ROWS
    assert b'rejected' not in resp.data.lower()


def test_text_import_over_byte_limit_rejected(admin_client, conv):
    """The text-area path enforces MAX_FILE_BYTES before parsing (#238), mirroring
    the old CSV upload's pre-read byte cap — a crafted POST cannot bypass it."""
    from seed_csv import MAX_FILE_BYTES
    big = 'a' * (MAX_FILE_BYTES + 1)
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, big)
    assert b'too much text' in resp.data.lower()
    assert mock.return_value.bulk_add_seeds.call_args is None


def test_mixed_parse_errors_and_row_limit_limit_fires_first(admin_client, conv):
    """When the paste exceeds MAX_ROWS AND has a parse error, the limit rejection
    fires first and the flash hints that parse errors may also be present so the
    admin fixes everything at once."""
    from seed_csv import MAX_ROWS
    overlong = 'a' * 281
    # First line is overlong (a parse error within the kept rows), followed by
    # enough lines to overflow the row limit.
    lines = [overlong] + [f'Statement {i}' for i in range(MAX_ROWS + 1)]
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, '\n'.join(lines))
    assert mock.return_value.bulk_add_seeds.call_args is None
    assert b'rejected' in resp.data.lower()
    assert b'maximum is' in resp.data.lower()
    assert b'parse error' in resp.data.lower()


# ── Deduplication against existing Polis statements ──────────────────────────

def test_text_import_sanitizes_and_deduplicates(admin_client, conv):
    existing = [{'txt': 'Already there', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        resp = _text_import(
            admin_client,
            conv.id,
            '<b>Hello</b>\nHello\n&equals;SUM(A1)\nAlready there',
        )
    assert b'already exists' in resp.data.lower()
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert texts_sent == ['Hello', 'SUM(A1)']


def test_skips_statements_already_in_polis(admin_client, conv):
    existing = [{'txt': 'Already there', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        resp = _text_import(admin_client, conv.id, 'Already there\nNew one')
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 1
    assert b'already exists' in resp.data.lower()
    assert b'1 imported' in resp.data


def test_dedup_is_case_insensitive(admin_client, conv):
    existing = [{'txt': 'Hello', 'mod': 1, 'is_seed': True,
                 'tid': 1, 'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}]
    with _mock_polis(existing_statements=([], existing, [])) as mock:
        _text_import(admin_client, conv.id, 'hello\nHello\nHELLO')
    # All three are case-fold duplicates of 'Hello' — none should be sent.
    assert mock.return_value.bulk_add_seeds.call_args is None or \
           mock.return_value.bulk_add_seeds.call_args[0][1] == []


def test_dedup_continues_when_polis_fetch_fails(admin_client, conv):
    """If get_statements raises, import proceeds without dedup and shows a warning."""
    with _mock_polis() as mock:
        # First call (import route) raises; second call (redirect view) succeeds.
        mock.return_value.get_statements.side_effect = [
            Exception('db down'),
            ([], [], []),
        ]
        resp = _text_import(admin_client, conv.id, 'Statement one\nStatement two')
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert len(texts_sent) == 2
    assert b'Could not check for existing statements' in resp.data


# ── Polis API failures ────────────────────────────────────────────────────────

def test_polis_api_failure_reported(admin_client, conv):
    """Per-statement Polis rejections (e.g. duplicates) show as 'Already in Polis, skipped'."""
    with _mock_polis(add_seed_side_effect=PolisServerError('timeout')):
        resp = _text_import(admin_client, conv.id, 'Statement one\nStatement two')
    assert b'already in polis' in resp.data.lower()
    assert b'0 imported' in resp.data.lower() or b'already existed' in resp.data.lower()


def test_partial_polis_failure_still_imports_others(admin_client, conv):
    """When some statements succeed and others are Polis-rejected, show partial success."""
    results = [None, PolisServerError('nope')]

    def side_effect(*a, **kw):
        r = results.pop(0)
        if r is not None:
            raise r

    with _mock_polis(add_seed_side_effect=side_effect):
        resp = _text_import(admin_client, conv.id, 'Good one\nBad one')
    assert b'1 imported' in resp.data
    assert b'already in polis' in resp.data.lower()


def test_banner_shows_skipped_count_when_mixed_with_successes(admin_client, conv):
    """When some statements succeed and one is Polis-rejected, the banner shows
    the correct counts and the per-statement flash explains the Polis skip."""
    def bulk_side_effect(conv_id, texts):
        return len(texts) - 1, [(texts[-1], PolisServerError('already exists'))]

    with _mock_polis() as mock:
        mock.return_value.bulk_add_seeds.side_effect = bulk_side_effect
        resp = _text_import(admin_client, conv.id, 'Good one\nAlso good\nBad one')
    # Banner: "✓ 2 imported — ⚠ 1 skipped"
    assert b'2 imported' in resp.data
    assert b'1 skipped' in resp.data
    assert b'already in polis' in resp.data.lower()


# ── Security ─────────────────────────────────────────────────────────────────

def test_xss_in_statement_text_is_escaped(admin_client, conv):
    with _mock_polis():
        resp = _text_import(admin_client, conv.id, '<script>alert(1)</script>')
    assert b'<script>' not in resp.data


def test_formula_injection_stripped_before_add_seed(admin_client, conv):
    with _mock_polis() as mock:
        _text_import(admin_client, conv.id, '=DANGEROUS')
    texts_sent = mock.return_value.bulk_add_seeds.call_args[0][1]
    assert texts_sent and not texts_sent[0].startswith('=')


def test_html_entity_formula_injection_stripped(admin_client, conv):
    # &equals; is the HTML entity for '=' — nh3 decodes it, so we must
    # re-strip formula prefixes after sanitisation.
    with _mock_polis() as mock:
        resp = _text_import(admin_client, conv.id, '&equals;SUM(A1)')
    # &equals; decodes to '=' via nh3; second-pass strip_formula_prefixes must remove it.
    assert mock.return_value.bulk_add_seeds.call_args is None or \
           all(not t.startswith('=') for t in mock.return_value.bulk_add_seeds.call_args[0][1])


def test_all_tags_text_produces_empty_string_and_is_not_sent(admin_client, conv):
    # A line that is only HTML tags becomes '' after nh3.clean — must not be
    # sent to Polis as an empty seed statement.
    with _mock_polis() as mock:
        _text_import(admin_client, conv.id, '<b></b>')
    call_args = mock.return_value.bulk_add_seeds.call_args
    assert call_args is None or call_args[0][1] == []


def test_nh3_induced_duplicate_sent_only_once(admin_client, conv):
    # '<b>Hello</b>' and 'Hello' both sanitize to 'Hello' — only one
    # should reach Polis.
    with _mock_polis() as mock:
        _text_import(admin_client, conv.id, '<b>Hello</b>\nHello')
    call_args = mock.return_value.bulk_add_seeds.call_args
    assert call_args is not None, "bulk_add_seeds should have been called"
    texts_sent = call_args[0][1]
    assert texts_sent.count('Hello') == 1
