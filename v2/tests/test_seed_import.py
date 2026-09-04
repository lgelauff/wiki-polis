"""Flask integration tests for POST /api/v1/admin/conversations/<id>/statement-imports.

Ported from the deleted text-area route
(POST /admin/conversations/<id>/statements/seed/import-text). The client now sends
a JSON array of statements instead of a newline-separated paste, so the textarea
parser and its byte cap are gone; everything after parsing -- dedup-vs-Polis,
Polis-failure handling, the row limit, sanitisation -- is unchanged and is what
these cover. The response is an outcome object rather than a flash banner:
{'imported', 'skippedExisting', 'skippedDuplicateInput', 'failedUpstream'}.

Three behaviours genuinely changed with the move, and the tests were rewritten to
the new behaviour rather than forced back to the old one:

  * A duplicate within one paste used to reject the whole batch. It is now
    skipped and counted in skippedDuplicateInput; the rest of the batch imports.
  * A line that sanitises to an empty string used to be dropped silently. It is
    now a 400 that names the offending statement.
  * If the existing-statement fetch fails, the import used to proceed WITHOUT
    dedup and show a warning. It now FAILS CLOSED with 503 and imports nothing.
    See test_dedup_fails_closed_when_polis_fetch_fails.

One test was dropped outright: test_text_import_over_byte_limit_rejected. The
#238 cap it covered was a pre-parse guard on the raw textarea body; MAX_FILE_BYTES
is now referenced by no production code and no MAX_CONTENT_LENGTH replaces it.
That is a lost guard, not a lost test -- see the port notes.
"""
from unittest.mock import MagicMock, patch

import pytest

from db import Conversation, db
from polis_admin import POLIS_NOT_CONFIGURED_MESSAGE, PolisServerError
from seed_csv import MAX_ROWS, MAX_TEXT_CHARS


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


_UNSET = object()


def _import(client, conv_id, statements):
    """POST a statement import. `statements` is the JSON array the SPA sends."""
    return client.post(
        f'/api/v1/admin/conversations/{conv_id}/statement-imports',
        json={'statements': statements},
    )


def _outcome(resp):
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']['outcome']


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()['error']


def _sent(mock):
    """The list of texts actually forwarded to Polis, or None if never called."""
    call = mock.return_value.bulk_add_seeds.call_args
    return None if call is None else call[0][1]


def _mock_polis(add_seed_side_effect=None, existing_statements=_UNSET):
    """Patch _polis_server_client (and the participant-client fallback).

    `existing_statements=None` simulates the dedup source being unavailable from
    BOTH the server client and the participant fallback, which is what makes
    import_seed_statements fail closed.
    """
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
    if existing_statements is _UNSET:
        mock_client.get_statements.return_value = ([], [], [])
    else:
        mock_client.get_statements.return_value = existing_statements

    from polis_admin import PolisParticipantError

    participant_client = MagicMock()
    participant_client.return_value.get_settings.return_value = {}
    if existing_statements is None:
        # The fallback must fail too, or it would supply the buckets instead.
        participant_client.return_value.get_statements.side_effect = (
            PolisParticipantError('unavailable')
        )
    else:
        participant_client.return_value.get_statements.return_value = (
            ([], [], []) if existing_statements is _UNSET else existing_statements
        )

    server_patch = patch('app._polis_server_client', return_value=mock_client)
    participant_patch = patch('app.PolisParticipantClient', participant_client)

    class _Both:
        def __enter__(self):
            started = server_patch.start()
            participant_patch.start()
            return started        # .return_value is mock_client

        def __exit__(self, *exc):
            participant_patch.stop()
            server_patch.stop()
            return False

    return _Both()


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_unauthenticated_is_refused(client, conv):
    """The Jinja route redirected to /login; the API refuses outright."""
    resp = _import(client, conv.id, ['hello'])
    assert resp.status_code == 403
    assert resp.get_json()['error']['code'] == 'forbidden'


def test_non_admin_forbidden(auth_client, conv):
    resp = _import(auth_client, conv.id, ['hello'])
    assert resp.status_code == 403


# ── Happy path ────────────────────────────────────────────────────────────────

def test_imports_statements(admin_client, conv):
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['Statement one', 'Statement two']))
    assert outcome['imported'] == 2
    assert len(_sent(mock)) == 2


def test_single_statement_is_counted_as_one(admin_client, conv):
    # The page said "1 statement imported" vs "2 statements imported"; the
    # grammar is the SPA's, the count is the server's.
    with _mock_polis():
        outcome = _outcome(_import(admin_client, conv.id, ['Only one']))
    assert outcome['imported'] == 1


def test_bulk_seed_surfaces_same_safe_polis_configuration_error(admin_client, conv):
    error = PolisServerError(
        'internal configuration detail',
        admin_message=POLIS_NOT_CONFIGURED_MESSAGE,
    )
    with _mock_polis() as mock:
        mock.return_value.bulk_add_seeds.side_effect = error
        resp = _import(admin_client, conv.id, ['A seed statement'])

    error_body = _error(resp, 502)
    assert error_body['code'] == 'upstream_unavailable'
    assert error_body['message'] == POLIS_NOT_CONFIGURED_MESSAGE
    # The internal detail must not leak to the admin, on any surface.
    assert b'internal configuration detail' not in resp.data


def test_blank_and_padded_entries_are_trimmed_and_dropped(admin_client, conv):
    # The textarea split on newlines and dropped blank lines; the array form keeps
    # the same normalisation for blank and padded entries.
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['One', '', 'Two', '  Three  ']))
    assert outcome['imported'] == 3
    assert _sent(mock) == ['One', 'Two', 'Three']


def test_seed_import_allowed_in_preparation(admin_client, conv):
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id, ['Prep seed']))
    assert outcome['imported'] == 1
    mock.return_value.bulk_add_seeds.assert_called_once()


def test_seed_import_allowed_during_submission(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id, ['Submission seed']))
    assert outcome['imported'] == 1
    mock.return_value.bulk_add_seeds.assert_called_once()


def test_seed_import_locked_after_submission_phase(admin_client, conv):
    conv.phase_personal_results = True
    db.session.commit()
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['Too late'])
    assert 'statement submission has ended' in _error(resp, 400)['message'].lower()
    assert _sent(mock) is None


def test_seed_import_locked_in_argument_phase(admin_client, conv):
    conv.phase_argument_mapping = True
    db.session.commit()
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['Too late'])
    assert 'statement submission has ended' in _error(resp, 400)['message'].lower()
    assert _sent(mock) is None


def test_single_seed_locked_when_conversation_closed(admin_client, conv):
    conv.active = False
    db.session.commit()
    with _mock_polis() as mock:
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/statements',
            json={'text': 'Closed seed', 'derivedFromId': None},
        )
    assert 'permanently closed' in _error(resp, 400)['message'].lower()
    mock.return_value.add_seed.assert_not_called()


def test_statements_read_reports_the_seed_lock(admin_client, conv):
    """The page hid the seed forms when locked; the server publishes the lock.

    Replaces test_statements_page_hides_seed_forms_when_locked, which asserted the
    absence of the form markup. The decision it depended on is in the payload.
    """
    conv.phase_cleanup = True
    db.session.commit()
    with _mock_polis():
        resp = admin_client.get(
            f'/api/v1/admin/conversations/{conv.id}/statements',
        )
    data = resp.get_json()['data']
    assert resp.status_code == 200
    assert data['capabilities']['seed'] is False
    assert data['seeding']['allowed'] is False
    assert 'statement submission has ended' in data['seeding']['lockReason'].lower()


def test_statements_read_publishes_the_import_limits(admin_client, conv):
    """The limits the form used to hard-code are served, so the client cannot drift."""
    with _mock_polis():
        data = admin_client.get(
            f'/api/v1/admin/conversations/{conv.id}/statements',
        ).get_json()['data']
    assert data['seeding']['allowed'] is True
    assert data['seeding']['maxStatementsPerImport'] == MAX_ROWS
    assert data['seeding']['maxCharactersPerStatement'] == MAX_TEXT_CHARS


# Deleted with the Jinja frontend: test_statements_page_describes_actual_seed_behavior
# asserted the exact help sentence on the statements page ("Adds a seed-marked
# statement that appears early in the voting sequence for participants.") and that
# the contradictory "not seed-marked" wording was absent. That copy is the SPA's;
# no server field carries it.


def test_empty_input_imports_nothing(admin_client, conv):
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['   ', '  '])
    assert _error(resp, 400)['code'] == 'validation_failed'
    assert _sent(mock) is None


# ── Row limits and per-row error reporting ────────────────────────────────────

def test_rejects_overlong_statement(admin_client, conv):
    long_text = 'x' * (MAX_TEXT_CHARS + 1)
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['Good', long_text])
    message = _error(resp, 400)['message']
    assert 'Statement 2' in message                  # names the offending row
    assert str(MAX_TEXT_CHARS) in message
    assert mock.return_value.bulk_add_seeds.call_count == 0


def test_duplicate_within_one_import_is_skipped_not_rejected(admin_client, conv):
    """CHANGED BEHAVIOUR (was test_text_import_duplicate_within_paste_rejects_batch).

    The textarea route rejected the entire batch on an in-paste duplicate, naming
    the offending row. The API skips the duplicate, counts it, and imports the
    rest. Asserted here as the new intended behaviour.
    """
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['hello', 'hello', 'world']))
    assert outcome['imported'] == 2
    assert outcome['skippedDuplicateInput'] == 1
    assert _sent(mock) == ['hello', 'world']


def test_enforces_row_limit(admin_client, conv):
    rows = [f'Statement {i}' for i in range(MAX_ROWS + 1)]
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, rows)
    message = _error(resp, 400)['message']
    assert str(MAX_ROWS) in message
    assert _sent(mock) is None


def test_exactly_max_rows_accepted(admin_client, conv):
    """Exactly MAX_ROWS valid statements import without rejection."""
    rows = [f'Statement {i}' for i in range(MAX_ROWS)]
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id, rows))
    assert outcome['imported'] == MAX_ROWS
    assert len(_sent(mock)) == MAX_ROWS


def test_row_limit_fires_before_per_row_validation(admin_client, conv):
    """When the import exceeds MAX_ROWS AND contains an invalid row, the limit is
    reported first — the admin is told the batch is too big before being told
    about individual rows, so they fix the size problem once."""
    overlong = 'a' * (MAX_TEXT_CHARS + 1)
    rows = [overlong] + [f'Statement {i}' for i in range(MAX_ROWS + 1)]
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, rows)
    message = _error(resp, 400)['message']
    assert str(MAX_ROWS) in message
    assert 'Statement 1' not in message              # the row error did not win
    assert _sent(mock) is None


# ── Deduplication against existing Polis statements ──────────────────────────

def _existing(*texts):
    return ([], [
        {'txt': text, 'mod': 1, 'is_seed': True, 'tid': index,
         'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}
        for index, text in enumerate(texts, start=1)
    ], [])


def test_sanitizes_and_deduplicates(admin_client, conv):
    with _mock_polis(existing_statements=_existing('Already there')) as mock:
        outcome = _outcome(_import(admin_client, conv.id, [
            '<b>Hello</b>', 'Hello', '&equals;SUM(A1)', 'Already there',
        ]))
    assert _sent(mock) == ['Hello', 'SUM(A1)']
    assert outcome['imported'] == 2
    assert outcome['skippedExisting'] == 1           # 'Already there'
    assert outcome['skippedDuplicateInput'] == 1     # '<b>Hello</b>' vs 'Hello'


def test_skips_statements_already_in_polis(admin_client, conv):
    with _mock_polis(existing_statements=_existing('Already there')) as mock:
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['Already there', 'New one']))
    assert _sent(mock) == ['New one']
    assert outcome['imported'] == 1
    assert outcome['skippedExisting'] == 1


def test_dedup_is_case_insensitive(admin_client, conv):
    with _mock_polis(existing_statements=_existing('Hello')) as mock:
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['hello', 'Hello', 'HELLO']))
    # All three are case-fold duplicates of the existing 'Hello', so nothing is
    # sent at all. Asserting the outcome (not just "bulk wasn't called") is what
    # keeps this honest: the old version passed even when the route had vanished.
    assert _sent(mock) is None
    assert outcome['imported'] == 0
    assert outcome['skippedExisting'] == 1
    assert outcome['skippedDuplicateInput'] == 2


def test_dedup_fails_closed_when_polis_fetch_fails(admin_client, conv):
    """CHANGED BEHAVIOUR (was test_dedup_continues_when_polis_fetch_fails).

    The Jinja route imported anyway when the existing-statement fetch failed,
    warning the admin that duplicates could not be checked. The API refuses the
    whole import with 503 and writes nothing.

    This is the strictly safer direction -- an unverified import can silently
    duplicate live statements -- and it looks deliberate: the API suite carries a
    purpose-written twin,
    test_admin_statements_api.py::test_seed_import_fails_closed_when_dedup_source_is_unavailable.
    It is still a user-visible behaviour change that converts a
    degraded-but-working import into a hard outage whenever Polis PG is
    unreachable, so it is flagged in the port notes for confirmation. Kept here as
    well as in the API suite because this is where the old, opposite behaviour was
    asserted, and the contrast is the point.
    """
    with _mock_polis(existing_statements=None) as mock:
        resp = _import(admin_client, conv.id, ['Statement one', 'Statement two'])

    assert _error(resp, 503)['code'] == 'verification_unavailable'
    assert _sent(mock) is None                       # nothing was imported


# ── Polis API failures ────────────────────────────────────────────────────────

def test_polis_api_failure_reported(admin_client, conv):
    """When every statement is rejected upstream, the import reports the failure."""
    with _mock_polis(add_seed_side_effect=PolisServerError('timeout')):
        resp = _import(admin_client, conv.id, ['Statement one', 'Statement two'])
    assert _error(resp, 502)['code'] == 'upstream_unavailable'


def test_partial_polis_failure_still_imports_others(admin_client, conv):
    """When some statements succeed and others are Polis-rejected, both are counted."""
    results = [None, PolisServerError('nope')]

    def side_effect(*a, **kw):
        r = results.pop(0)
        if r is not None:
            raise r

    with _mock_polis(add_seed_side_effect=side_effect):
        outcome = _outcome(_import(admin_client, conv.id, ['Good one', 'Bad one']))
    assert outcome['imported'] == 1
    assert outcome['failedUpstream'] == 1


def test_outcome_counts_successes_and_upstream_skips_together(admin_client, conv):
    """The banner read "2 imported - 1 skipped"; those two numbers are the outcome."""
    def bulk_side_effect(conv_id, texts):
        return len(texts) - 1, [(texts[-1], PolisServerError('already exists'))]

    with _mock_polis() as mock:
        mock.return_value.bulk_add_seeds.side_effect = bulk_side_effect
        outcome = _outcome(_import(admin_client, conv.id,
                                   ['Good one', 'Also good', 'Bad one']))
    assert outcome['imported'] == 2
    assert outcome['failedUpstream'] == 1


# ── Security ─────────────────────────────────────────────────────────────────

def test_xss_in_statement_text_never_reaches_polis(admin_client, conv):
    """A script payload is stripped to nothing and the import is refused.

    The Jinja version asserted only that '<script>' was absent from the rendered
    page, which the empty SPA shell satisfied for free. What matters is that the
    payload never reaches Polis: nh3 removes the script element and its contents,
    leaving an empty statement, which the import then rejects outright.
    """
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['<script>alert(1)</script>'])
    assert 'empty after sanitization' in _error(resp, 400)['message'].lower()
    assert _sent(mock) is None
    assert b'<script>' not in resp.data


def test_formula_injection_stripped_before_add_seed(admin_client, conv):
    with _mock_polis() as mock:
        _outcome(_import(admin_client, conv.id, ['=DANGEROUS']))
    assert _sent(mock) == ['DANGEROUS']


def test_html_entity_formula_injection_stripped(admin_client, conv):
    # &equals; is the HTML entity for '=' — nh3 decodes it, so the formula prefix
    # must be stripped again after sanitisation.
    with _mock_polis() as mock:
        _outcome(_import(admin_client, conv.id, ['&equals;SUM(A1)']))
    assert _sent(mock) == ['SUM(A1)']


def test_text_that_sanitizes_to_nothing_is_rejected(admin_client, conv):
    """CHANGED BEHAVIOUR (was test_all_tags_text_produces_empty_string_and_is_not_sent).

    '<b></b>' becomes '' after nh3.clean. The textarea route dropped such a line
    silently; the API rejects the import and names the statement. Either way it
    must never reach Polis as an empty seed.
    """
    with _mock_polis() as mock:
        resp = _import(admin_client, conv.id, ['<b></b>'])
    message = _error(resp, 400)['message']
    assert 'Statement 1' in message
    assert 'empty after sanitization' in message.lower()
    assert _sent(mock) is None


def test_nh3_induced_duplicate_sent_only_once(admin_client, conv):
    # '<b>Hello</b>' and 'Hello' both sanitize to 'Hello' — only one
    # should reach Polis.
    with _mock_polis() as mock:
        outcome = _outcome(_import(admin_client, conv.id, ['<b>Hello</b>', 'Hello']))
    texts_sent = _sent(mock)
    assert texts_sent is not None, 'bulk_add_seeds should have been called'
    assert texts_sent.count('Hello') == 1
    assert outcome['skippedDuplicateInput'] == 1
